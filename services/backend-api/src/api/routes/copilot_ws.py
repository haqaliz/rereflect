"""
Copilot WebSocket endpoint (M2.2 AI Copilot).

Protocol: wss://{host}/ws/copilot?token={jwt}

Client -> Server messages:
- query: Submit a question
- stop: Cancel ongoing generation
- regenerate: Regenerate the last AI response

Server -> Client messages:
- status: Processing status update
- stream: Streaming token delta
- structured_data: Table/chart/link data
- error: Error with suggestions
"""

import json
import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Optional

import openai  # imported at module level so tests can patch src.api.routes.copilot_ws.openai

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.api.auth import decode_access_token
from src.models.user import User
from src.models.organization import Organization
from src.models.conversation import Conversation
from src.models.conversation_message import ConversationMessage
from src.services.ws_connection_manager import manager
from src.services.copilot_rate_limiter import check_rate_limits
from src.services.copilot.intent_classifier import IntentClassifier
from src.services.copilot.context_resolver import ContextResolver
from src.services.copilot.sql_generator import SQLGenerator
from src.services.copilot.sql_executor import SQLExecutor, QueryTimeoutError, QueryExecutionError
from src.services.copilot.template_matcher import TemplateMatcher
from src.services.copilot.template_saver import TemplateSaver
from src.services.copilot.response_formatter import format_response
from src.services.copilot.report_generator import ReportGenerator
from src.models.subscription import Subscription
from src.models.report import Report
from src.config.plans import has_feature
from src.services.embeddings import resolve_embedding_provider
from src.services.copilot.llm_resolver import resolve_generation_llm, LLMConfig

logger = logging.getLogger(__name__)

router = APIRouter(tags=["copilot-ws"])

HEARTBEAT_INTERVAL = 30  # seconds
IDLE_TIMEOUT = 300  # 5 minutes

# Keywords that suggest the user wants a visual chart
_CHART_KEYWORDS = {"chart", "graph", "plot", "visual", "visualize", "compare", "trend", "breakdown", "distribution"}


# -- LLM streaming ------------------------------------------------------------


_DUMMY_LLM_KEY = "ollama"  # non-empty placeholder required by the OpenAI SDK for local endpoints


async def call_llm_stream(
    messages: list,
    provider: str = "openai",
    model: str = "gpt-4o-mini",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
):
    """
    Stream tokens from the configured LLM provider.
    Yields chunk objects with .choices[0].delta.content attribute.
    Can be patched in tests.

    Supports two modes:
    - Local / OpenAI-compatible (base_url set, api_key=None): connects to a
      local endpoint such as Ollama or LM Studio.  Uses a dummy key placeholder
      because the OpenAI SDK requires a non-empty api_key even for local calls.
    - Cloud BYOK (api_key set, base_url=None): standard OpenAI or compatible
      cloud endpoint with the org's own key.
    """
    if base_url:
        # Local / OpenAI-compatible endpoint — keyless is allowed
        key = api_key or _DUMMY_LLM_KEY
        logger.info(
            f"call_llm_stream: local provider={provider}, model={model}, "
            f"base_url={base_url}, messages={len(messages)}"
        )
        client = openai.AsyncOpenAI(api_key=key, base_url=base_url, timeout=60.0)
    else:
        # Cloud BYOK path — no local base_url
        key = api_key or ""
        masked_key = f"***{key[-4:]}" if key and len(key) > 4 else "EMPTY"
        logger.info(
            f"call_llm_stream: provider={provider}, model={model}, "
            f"key={masked_key}, messages={len(messages)}"
        )
        client = openai.AsyncOpenAI(api_key=key, timeout=60.0)

    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            max_tokens=1000,
            temperature=0.7,
        )
        logger.info("call_llm_stream: stream created, iterating chunks...")
        async for chunk in stream:
            yield chunk
        logger.info("call_llm_stream: stream completed")
    except Exception as e:
        logger.error(f"call_llm_stream error: {type(e).__name__}: {e}")
        raise


# -- Authentication -----------------------------------------------------------


def _authenticate_ws(token: Optional[str], db: Session):
    """Decode JWT and return (user, org) or (None, None) if invalid."""
    if not token:
        return None, None

    payload = decode_access_token(token)
    if not payload:
        return None, None

    user_id = payload.get("user_id")
    if not user_id:
        return None, None

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None, None

    return user, user.organization


# -- Report handler -----------------------------------------------------------


async def _handle_report(
    websocket: WebSocket,
    db: Session,
    user,
    org,
    conversation: "Conversation",
    content: str,
    context_scope: str,
    message_id: str,
    plan: str,
    provider: str,
    model: str,
    api_key: Optional[str],
    base_url: Optional[str] = None,
) -> None:
    """
    Handle a 'report' intent: generate a structured AI report, stream section
    narratives, persist the Report and a ConversationMessage, then send
    report_complete.

    Plan gate: Business+ only.  Free/Pro receive an upgrade prompt instead.
    """
    # 1. Plan gate
    if not has_feature(plan, "ai_reports"):
        # Stream an upgrade message (same pattern as general intent)
        upgrade_msg = (
            "Report generation is available on the Business plan. "
            "Upgrade to generate comprehensive PDF reports from your feedback data."
        )
        await manager.send(websocket, {
            "type": "status",
            "message_id": message_id,
            "status": "generating",
        })
        await manager.send(websocket, {
            "type": "stream",
            "message_id": message_id,
            "delta": upgrade_msg,
            "done": False,
        })
        await manager.send(websocket, {
            "type": "stream",
            "message_id": message_id,
            "delta": "",
            "done": True,
            "metadata": {"query_type": "report", "model": model, "provider": provider},
        })
        # Persist only the AI assistant message (user message already saved by _handle_query step 1)
        _persist_report_assistant_message(
            db=db,
            conversation=conversation,
            ai_content=upgrade_msg,
            context_scope=context_scope,
            query_type="report",
        )
        return

    # 2. Extract report type and date range from query
    generator = ReportGenerator()
    report_type = generator.extract_report_type(content)
    date_range_days = generator.extract_date_range(content)

    await manager.send(websocket, {
        "type": "status",
        "message_id": message_id,
        "status": "generating",
    })

    try:
        # 3. Generate report data (synchronous DB queries)
        # Run in the current thread to avoid SQLite thread-safety issues
        # and to keep the sync SQLAlchemy session on the same thread.
        report_data = generator.generate(
            db=db,
            org_id=org.id,
            report_type=report_type,
            date_range_days=date_range_days,
        )

        title = report_data.get("title", f"{report_type.replace('_', ' ').title()} Report")
        sections = report_data.get("sections", [])
        total_sections = len(sections)

        # 4. Build a single LLM prompt with ALL section data and stream the
        #    response using the standard "stream" message type that the
        #    frontend already handles.
        import json as _json

        # Compile data summaries for all sections
        section_summaries = []
        for section in sections:
            data_str = _json.dumps(section.get("data", {}), default=str)[:600]
            section_summaries.append(
                f"### {section['heading']}\n{data_str}"
            )

        llm_messages = [
            {
                "role": "system",
                "content": (
                    "You are a data analyst writing a feedback analysis report. "
                    "Write in a professional, concise tone. Use specific numbers. "
                    "Do not make up data. Use markdown headings (##) for each section."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Write a {report_type.replace('_', ' ')} report for the last "
                    f"{date_range_days} days.\n\n"
                    f"Report title: {title}\n\n"
                    f"Data per section:\n\n"
                    + "\n\n".join(section_summaries)
                    + "\n\nWrite 2-3 paragraphs per section with specific numbers. "
                    "Use ## headings for each section."
                ),
            },
        ]

        # Stream the full report as regular chat stream messages
        full_content = ""
        try:
            async for chunk in call_llm_stream(
                messages=llm_messages,
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
            ):
                delta = ""
                if hasattr(chunk, "choices") and chunk.choices:
                    delta_obj = chunk.choices[0].delta
                    if hasattr(delta_obj, "content") and delta_obj.content:
                        delta = delta_obj.content
                if delta:
                    full_content += delta
                    await manager.send(websocket, {
                        "type": "stream",
                        "message_id": message_id,
                        "delta": delta,
                        "done": False,
                    })
        except Exception as llm_err:
            logger.warning(f"Report LLM stream failed: {llm_err}")
            # Fallback: build a text summary from the raw data
            fallback_parts = [f"## {title}\n"]
            for section in sections:
                fallback_parts.append(f"### {section['heading']}")
                data = section.get("data", {})
                if isinstance(data, dict) and "rows" in data:
                    for row in data["rows"][:5]:
                        fallback_parts.append(f"- {row}")
            full_content = "\n\n".join(fallback_parts)
            await manager.send(websocket, {
                "type": "stream",
                "message_id": message_id,
                "delta": full_content,
                "done": False,
            })

        # Send final stream done message
        await manager.send(websocket, {
            "type": "stream",
            "message_id": message_id,
            "delta": "",
            "done": True,
            "metadata": {
                "query_type": "report",
                "model": model,
                "provider": provider,
                "report_type": report_type,
                "date_range_days": date_range_days,
            },
        })

        # Build completed sections with narrative from LLM content
        completed_sections = []
        for section in sections:
            completed_sections.append({**section, "narrative": ""})

        # 5. Save Report to DB
        report_record = Report(
            organization_id=org.id,
            created_by_user_id=user.id,
            conversation_id=conversation.id,
            report_type=report_type,
            date_range_days=date_range_days,
            title=title,
            sections=completed_sections,
            report_metadata={
                "generated_at": datetime.utcnow().isoformat(),
                "model_used": model,
                "date_range_days": date_range_days,
            },
            pdf_generated=False,
        )
        db.add(report_record)
        db.commit()
        db.refresh(report_record)

        # 6. Persist ConversationMessage with query_type="report"
        _persist_report_assistant_message(
            db=db,
            conversation=conversation,
            ai_content=full_content,
            context_scope=context_scope,
            query_type="report",
        )

    except Exception as e:
        logger.error(f"Report generation error: {e}", exc_info=True)
        try:
            await manager.send(websocket, {
                "type": "error",
                "message_id": message_id,
                "error": f"Report generation failed: {str(e)}",
                "suggestions": [
                    "Try again in a few seconds",
                    "Check your API key configuration in settings",
                ],
            })
        except Exception:
            pass


def _persist_report_assistant_message(
    db: Session,
    conversation: "Conversation",
    ai_content: str,
    context_scope: str,
    query_type: str,
) -> None:
    """
    Persist the AI assistant ConversationMessage for a report response.
    The user message was already persisted by _handle_query step 1.
    Silently ignores errors to avoid disrupting WebSocket flow.
    """
    try:
        # Check session health
        from sqlalchemy import text as sa_text
        try:
            db.execute(sa_text("SELECT 1"))
        except Exception:
            db.rollback()

        ai_msg = ConversationMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=ai_content,
            context_scope=context_scope,
            query_type=query_type,
            created_at=datetime.utcnow(),
        )
        db.add(ai_msg)
        conversation.updated_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to persist report assistant message: {e}")
        try:
            db.rollback()
        except Exception:
            pass


# -- Query handler ------------------------------------------------------------


async def _handle_query(
    websocket: WebSocket,
    db: Session,
    user: User,
    org: Organization,
    conversation: Conversation,
    content: str,
    context_scope: str,
    message_id: str,
) -> None:
    """Classify intent, run pipeline (SQL or general), stream response."""
    start_time = time.time()

    try:
        # 1. Persist user message
        user_msg = ConversationMessage(
            conversation_id=conversation.id,
            role="user",
            content=content,
            context_scope=context_scope,
            created_at=datetime.utcnow(),
        )
        db.add(user_msg)
        db.commit()
        db.refresh(user_msg)

        # 2. Send processing status
        await manager.send(websocket, {
            "type": "status",
            "message_id": message_id,
            "status": "processing",
        })

        # 3. Classify intent
        classifier = IntentClassifier()
        classification = classifier.classify(content)
        intent = classification["intent"]
        logger.info(f"_handle_query: intent={intent}, confidence={classification['confidence']:.2f}")

        # 4. Get org plan
        plan = "free"
        try:
            sub = db.query(Subscription).filter_by(organization_id=org.id).first()
            if sub and sub.plan:
                plan = sub.plan
        except Exception:
            pass

        # 4b. If intent == "report", delegate to the report pipeline
        if intent == "report":
            # Resolve LLM config (local-capable)
            _llm_cfg = resolve_generation_llm(org.id, db)
            if not _llm_cfg.is_configured:
                await websocket.send_json({
                    "type": "error",
                    "message": (
                        "No AI model configured. "
                        "Please configure a model in Settings → AI."
                    ),
                })
                return

            await _handle_report(
                websocket=websocket,
                db=db,
                user=user,
                org=org,
                conversation=conversation,
                content=content,
                context_scope=context_scope,
                message_id=message_id,
                plan=plan,
                provider=_llm_cfg.provider,
                model=_llm_cfg.model,
                api_key=_llm_cfg.api_key,
                base_url=_llm_cfg.base_url,
            )
            return

        # 5. Resolve context
        resolver = ContextResolver()
        mentions = resolver.parse_mentions(content)

        history = (
            db.query(ConversationMessage)
            .filter(ConversationMessage.conversation_id == conversation.id)
            .order_by(ConversationMessage.created_at)
            .limit(20)
            .all()
        )
        conversation_history = [
            {"role": msg.role, "content": msg.content} for msg in history
        ]

        # Use first scope for context resolver (handles comma-separated)
        primary_scope = context_scope.split(",")[0] if context_scope else "all_data"
        context = resolver.build_context(primary_scope, org.id, db, mentions, conversation_history)

        # 6. Resolve LLM provider/model for org (local-capable)
        llm_cfg = resolve_generation_llm(org.id, db)
        if not llm_cfg.is_configured:
            await websocket.send_json({
                "type": "error",
                "message": (
                    "No AI model configured. "
                    "Please configure a model in Settings → AI."
                ),
            })
            return

        provider = llm_cfg.provider
        model = llm_cfg.model
        api_key = llm_cfg.api_key
        base_url = llm_cfg.base_url

        logger.info(
            f"_handle_query: provider={provider}, model={model}, "
            f"local={'yes' if base_url else 'no'}, "
            f"key={'***' + api_key[-4:] if api_key and len(api_key) > 4 else 'EMPTY'}"
        )

        # 7. Pipeline: data/analysis vs general
        sql_generated = None
        template_id = None
        structured_data_payload = None
        query_type = intent
        sql_columns = None
        sql_rows = None
        sql_gen_error = None  # reason when SQL generation/validation fails

        # Resolve embedding provider once for this request (None = unconfigured org, degrade gracefully)
        resolved_embedder = None
        try:
            resolved_embedder = resolve_embedding_provider(org.id, db)
        except Exception as emb_err:
            logger.debug(f"Embedding provider resolution failed, degrading: {emb_err}")

        if intent in ("data", "analysis"):
            # 7a. Try template matching (fast path — may fail if no embeddings/tables)
            template_match = None
            try:
                matcher = TemplateMatcher()
                template_match = await asyncio.to_thread(
                    matcher.find_match, content, org.id, db, resolved_embedder
                )
            except Exception as e:
                logger.info(f"Template matching skipped: {e}")
                try:
                    db.rollback()
                except Exception:
                    pass

            # 7b. Get SQL — from template or generate via LLM
            sql = None
            params = {"org_id": org.id}

            if template_match:
                sql = template_match["sql_query"]
                template_id = template_match.get("template_id")
                query_type = "data"
                logger.info(
                    f"Template match: id={template_id}, similarity={template_match['similarity']:.3f}"
                )
            else:
                generator = SQLGenerator()
                gen_result = await asyncio.to_thread(
                    generator.generate,
                    question=content,
                    org_id=org.id,
                    plan=plan,
                    context=context,
                    api_key=api_key,
                    model=model,
                    base_url=base_url,
                )
                if gen_result["sql"]:
                    sql = gen_result["sql"]
                    params = gen_result["parameters"]
                    query_type = gen_result["query_type"]
                    sql_generated = sql
                    logger.info(f"SQL generated: type={query_type}, sql={sql[:120]}")
                elif gen_result["error"]:
                    sql_gen_error = gen_result["error"]
                    logger.warning(f"SQL generation failed: {sql_gen_error}")

            # 7c. Execute SQL
            if sql:
                try:
                    executor = SQLExecutor()
                    exec_result = executor.execute(sql, params, db)
                    sql_columns = exec_result["columns"]
                    sql_rows = exec_result["rows"]
                    logger.info(
                        f"SQL executed: {exec_result['row_count']} rows, "
                        f"truncated={exec_result['truncated']}"
                    )
                except (QueryTimeoutError, QueryExecutionError) as e:
                    logger.warning(f"SQL execution failed: {e}")
                    db.rollback()  # Reset aborted transaction so later DB ops work

            # 7d. Format structured data (table + chart) — conditionally
            if sql_columns is not None and sql_rows is not None:
                row_count = len(sql_rows)
                # Skip table/chart for single-value results (text summary is enough)
                include_table = row_count >= 2
                # Only include chart if 3+ rows AND query mentions visualization
                query_lower = content.lower()
                wants_chart = any(kw in query_lower for kw in _CHART_KEYWORDS)
                include_chart = row_count >= 3 and wants_chart

                formatted = format_response(
                    text="",
                    sql_columns=sql_columns,
                    sql_rows=sql_rows,
                    include_table=include_table,
                    include_chart=include_chart,
                )
                structured_data_payload = formatted["structured_data"] or None

        # 8. Build LLM messages based on pipeline results
        if sql_columns is not None and sql_rows is not None and len(sql_rows) > 0:
            # Data query succeeded — LLM summarizes actual results
            formatted_rows = ""
            for row in sql_rows[:50]:
                formatted_rows += " | ".join(str(v) for v in row) + "\n"

            llm_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an AI assistant for the Rereflect customer feedback platform.\n"
                        "You just ran a database query for the user. Here are the results:\n\n"
                        f"Columns: {', '.join(sql_columns)}\n"
                        f"Data ({len(sql_rows)} rows):\n{formatted_rows}\n"
                        "Summarize these results in a clear, concise way. Reference specific numbers.\n"
                        "If the data shows trends or notable patterns, mention them.\n"
                        "Keep your response under 200 words."
                    ),
                },
                {"role": "user", "content": content},
            ]
        elif intent in ("data", "analysis"):
            # Data intent but SQL failed or returned empty — give a context-aware response.
            # When the failure was a safety-check violation (local/weak model produced
            # invalid SQL), be honest about it rather than pretending the data is absent.
            safety_failed = (
                sql_gen_error is not None
                and "safety check" in sql_gen_error.lower()
            )

            if safety_failed:
                # Honest weak-model UX: tell the user the model couldn't produce safe SQL
                system_content = (
                    "You are an AI assistant for the Rereflect customer feedback platform.\n"
                    f"Context about the organization's data:\n{context}\n\n"
                    "I couldn't turn that question into a safe, valid SQL query with the "
                    "current model. This can happen with smaller or less capable local models.\n"
                    "A stronger model typically improves results.\n"
                    "Please acknowledge this honestly, suggest the user try rephrasing, and "
                    "briefly describe what data is available to help them ask a better question."
                )
            else:
                # Generic fallback: SQL returned empty or generation failed for other reasons
                system_content = (
                    "You are an AI assistant for the Rereflect customer feedback platform.\n"
                    f"Here is context about the organization's data:\n{context}\n\n"
                    "The user asked a data question but the query returned no results.\n"
                    "Help them understand what data is available and suggest alternative questions."
                )

            llm_messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": content},
            ]
        else:
            # General intent — conversational with context
            llm_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a helpful AI assistant for Rereflect, a customer feedback "
                        "analysis platform.\n"
                        f"Here is context about the organization:\n{context}\n\n"
                        "Help users with questions about the platform, their data, and "
                        "feedback analysis. Be concise and helpful."
                    ),
                },
            ] + [
                {"role": msg.role, "content": msg.content}
                for msg in history
            ]

        # 9. Stream LLM response
        full_content = ""
        tokens_in = 0
        tokens_out = 0
        cost_cents = 0.0

        await manager.send(websocket, {
            "type": "status",
            "message_id": message_id,
            "status": "generating",
        })

        chunk_count = 0
        async for chunk in call_llm_stream(
            messages=llm_messages,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
        ):
            delta = ""
            if hasattr(chunk, "choices") and chunk.choices:
                delta_obj = chunk.choices[0].delta
                if hasattr(delta_obj, "content") and delta_obj.content:
                    delta = delta_obj.content

            if delta:
                chunk_count += 1
                full_content += delta
                await manager.send(websocket, {
                    "type": "stream",
                    "message_id": message_id,
                    "delta": delta,
                    "done": False,
                })

        latency_ms = int((time.time() - start_time) * 1000)
        logger.info(
            f"_handle_query: stream done, {chunk_count} chunks, "
            f"{len(full_content)} chars, {latency_ms}ms"
        )

        # 10. Final stream message with metadata
        await manager.send(websocket, {
            "type": "stream",
            "message_id": message_id,
            "delta": "",
            "done": True,
            "metadata": {
                "model": model,
                "provider": provider,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_cents": cost_cents,
                "latency_ms": latency_ms,
                "query_type": query_type,
                "template_id": template_id,
                "sql_generated": sql_generated,
            },
        })

        # 11. Send structured_data if we have tables/charts
        if structured_data_payload:
            await manager.send(websocket, {
                "type": "structured_data",
                "message_id": message_id,
                "data": {
                    "text": full_content,
                    "structured_data": structured_data_payload,
                },
            })

        # 12. Persist AI response (ensure clean transaction state first)
        try:
            # Check if session is usable; rollback if previous ops left it dirty
            db.execute(sa_text("SELECT 1"))
        except Exception:
            db.rollback()

        ai_msg = ConversationMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=full_content,
            structured_data=structured_data_payload if structured_data_payload else None,
            context_scope=context_scope,
            query_type=query_type,
            template_id=int(template_id) if template_id else None,
            sql_generated=sql_generated,
            llm_provider=provider,
            llm_model=model,
            tokens_in=tokens_in or None,
            tokens_out=tokens_out or None,
            latency_ms=latency_ms,
            created_at=datetime.utcnow(),
        )
        db.add(ai_msg)
        conversation.updated_at = datetime.utcnow()
        db.commit()

        # 13. Save template for learning (non-blocking, never fails the response)
        if sql_generated and full_content and intent in ("data", "analysis"):
            try:
                saver = TemplateSaver()
                await asyncio.to_thread(
                    saver.save_template,
                    sql_query=sql_generated,
                    question=content,
                    description=f"Auto: {content[:100]}",
                    parameter_schema={"org_id": "integer"},
                    created_by="llm",
                    org_id=org.id,
                    db=db,
                    embedder=resolved_embedder,
                )
                logger.info(f"Template saved for: {content[:50]}")
            except Exception as e:
                logger.debug(f"Template save skipped: {e}")

        # Record usage if we matched a template
        if template_id:
            try:
                saver = TemplateSaver()
                saver.record_template_usage(int(template_id), db)
            except Exception:
                pass

    except asyncio.CancelledError:
        logger.info(f"Query cancelled: message_id={message_id}")
        raise
    except Exception as e:
        logger.error(f"Query error: {e}", exc_info=True)
        try:
            await manager.send(websocket, {
                "type": "error",
                "message_id": message_id,
                "error": f"Query failed: {str(e)}",
                "suggestions": [
                    "Try rephrasing your question",
                    "Check your API key configuration in settings",
                    "Try again in a few seconds",
                ],
            })
        except Exception:
            pass


# -- WebSocket endpoint -------------------------------------------------------


@router.websocket("/ws/copilot")
async def copilot_ws(
    websocket: WebSocket,
    token: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Real-time AI Copilot WebSocket endpoint.
    Authenticate via ?token={jwt} query parameter.
    """
    user, org = _authenticate_ws(token, db)
    if user is None or org is None:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    await manager.connect(websocket, user.id)
    logger.info(f"Copilot WS connected: user_id={user.id} org_id={org.id}")

    active_generation: Optional[asyncio.Task] = None
    last_activity = time.time()

    try:
        while True:
            if time.time() - last_activity > IDLE_TIMEOUT:
                await websocket.close(code=1000, reason="Idle timeout")
                break

            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=HEARTBEAT_INTERVAL,
                )
                last_activity = time.time()
            except asyncio.TimeoutError:
                try:
                    await manager.send(websocket, {"type": "ping"})
                except Exception:
                    break
                continue

            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send(websocket, {
                    "type": "error",
                    "error": "Invalid JSON message",
                    "suggestions": ["Ensure your message is valid JSON"],
                })
                continue

            msg_type = message.get("type")
            message_id = message.get("message_id", str(uuid.uuid4()))

            if msg_type == "query":
                if active_generation and not active_generation.done():
                    active_generation.cancel()

                rate_error = check_rate_limits(user.id, org, db)
                if rate_error:
                    await manager.send(websocket, {
                        "type": "error",
                        "message_id": message_id,
                        "error": rate_error,
                        "suggestions": [
                            "Upgrade to Pro for unlimited daily queries",
                            "Try again tomorrow",
                        ],
                    })
                    continue

                conversation_id = message.get("conversation_id")
                if not conversation_id:
                    await manager.send(websocket, {
                        "type": "error",
                        "message_id": message_id,
                        "error": "conversation_id is required",
                        "suggestions": ["Create a conversation via POST /api/v1/conversations"],
                    })
                    continue

                conversation = db.query(Conversation).filter(
                    Conversation.public_id == conversation_id,
                    Conversation.organization_id == org.id,
                    Conversation.is_active == True,
                ).first()

                if not conversation:
                    await manager.send(websocket, {
                        "type": "error",
                        "message_id": message_id,
                        "error": "Conversation not found or access denied",
                        "suggestions": ["Check the conversation ID and try again"],
                    })
                    continue

                content = message.get("content", "")
                context_scope = message.get("context_scope", "all_data")

                active_generation = asyncio.create_task(
                    _handle_query(
                        websocket=websocket,
                        db=db,
                        user=user,
                        org=org,
                        conversation=conversation,
                        content=content,
                        context_scope=context_scope,
                        message_id=message_id,
                    )
                )

                def _on_task_done(task: asyncio.Task) -> None:
                    if task.cancelled():
                        return
                    exc = task.exception()
                    if exc:
                        logger.error(f"Unhandled query task error: {type(exc).__name__}: {exc}")

                active_generation.add_done_callback(_on_task_done)

            elif msg_type == "stop":
                if active_generation and not active_generation.done():
                    active_generation.cancel()
                    await manager.send(websocket, {
                        "type": "status",
                        "message_id": message_id,
                        "status": "stopped",
                    })

            elif msg_type == "regenerate":
                await manager.send(websocket, {
                    "type": "error",
                    "message_id": message_id,
                    "error": "Regenerate not yet implemented",
                    "suggestions": ["Send a new query to continue"],
                })

            else:
                await manager.send(websocket, {
                    "type": "error",
                    "message_id": message_id,
                    "error": f"Unknown message type: {msg_type!r}",
                    "suggestions": ["Valid types: query, stop, regenerate"],
                })

    except WebSocketDisconnect:
        logger.info(f"Copilot WS disconnected: user_id={user.id}")
    finally:
        manager.disconnect(websocket, user.id)
        if active_generation and not active_generation.done():
            active_generation.cancel()
