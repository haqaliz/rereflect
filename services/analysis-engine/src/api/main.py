"""FastAPI application for feedback analysis."""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
from dotenv import load_dotenv

from ..analyzer import FeedbackAnalyzer, FeedbackInput, AnalysisResult

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI(
    title="Customer Feedback Analyzer API",
    description="AI-powered customer feedback analysis API for SaaS/app businesses",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize analyzer
ENABLE_CLUSTERING = os.getenv("ENABLE_CLUSTERING", "false").lower() == "true"
URGENT_THRESHOLD = float(os.getenv("URGENT_SENTIMENT_THRESHOLD", "-0.7"))
VERY_NEGATIVE_THRESHOLD = float(os.getenv("VERY_NEGATIVE_THRESHOLD", "-0.5"))

analyzer = FeedbackAnalyzer(
    enable_clustering=ENABLE_CLUSTERING,
    urgent_threshold=URGENT_THRESHOLD,
    very_negative_threshold=VERY_NEGATIVE_THRESHOLD
)


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Customer Feedback Analyzer API",
        "version": "1.0.0",
        "endpoints": {
            "analyze": "/api/v1/analyze",
            "health": "/health"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "clustering_enabled": ENABLE_CLUSTERING
    }


@app.post("/api/v1/analyze", response_model=AnalysisResult)
async def analyze_feedback(feedback_input: FeedbackInput):
    """
    Analyze customer feedback and return insights.

    This endpoint performs comprehensive analysis on customer feedback including:
    - Pain point extraction and clustering
    - Feature request identification
    - Sentiment analysis with trends
    - Urgent feedback flagging
    - Optional topic clustering

    Args:
        feedback_input: JSON payload containing feedback entries

    Returns:
        AnalysisResult: Complete analysis with pain points, feature requests,
                       sentiment summary, urgent items, and optional clusters

    Raises:
        HTTPException: If analysis fails
    """
    # Validate input first (before try block)
    if not feedback_input.feedback:
        raise HTTPException(
            status_code=400,
            detail="No feedback items provided in input"
        )

    try:
        # Perform analysis
        result = analyzer.analyze(feedback_input)

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )


@app.post("/api/v1/analyze/quick", response_model=dict)
async def quick_analyze(feedback_input: FeedbackInput):
    """
    Quick analysis returning only summary statistics.

    Useful for dashboards that need fast overview metrics without
    detailed clustering and extraction.

    Args:
        feedback_input: JSON payload containing feedback entries

    Returns:
        dict: Summary statistics including sentiment breakdown and counts
    """
    # Validate input first (before try block)
    if not feedback_input.feedback:
        raise HTTPException(
            status_code=400,
            detail="No feedback items provided in input"
        )

    try:
        result = analyzer.analyze(feedback_input)

        # Return simplified summary
        return {
            "total_feedback": result.total_feedback_count,
            "sentiment": {
                "positive_percent": result.sentiment_summary.positive_percent,
                "neutral_percent": result.sentiment_summary.neutral_percent,
                "negative_percent": result.sentiment_summary.negative_percent
            },
            "pain_points_count": len(result.common_pain_points),
            "feature_requests_count": len(result.feature_requests),
            "urgent_feedback_count": len(result.urgent_feedback),
            "top_pain_point": result.common_pain_points[0].issue if result.common_pain_points else None,
            "top_feature_request": result.feature_requests[0].feature if result.feature_requests else None
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Quick analysis failed: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))

    uvicorn.run(app, host=host, port=port)
