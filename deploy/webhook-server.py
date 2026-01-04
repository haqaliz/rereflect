#!/usr/bin/env python3
"""
Simple GitHub Webhook Server for auto-deployment.
Listens for push events and triggers deployment script.

Run with: python3 webhook-server.py
Or as systemd service (see deploy/rereflect-webhook.service)
"""

import hashlib
import hmac
import json
import os
import subprocess
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

# Configuration
PORT = int(os.environ.get('WEBHOOK_PORT', 9000))
SECRET = os.environ.get('WEBHOOK_SECRET', 'change-this-secret')
DEPLOY_SCRIPT = os.environ.get('DEPLOY_SCRIPT', '/opt/rereflect/deploy/deploy.sh')
ALLOWED_BRANCHES = os.environ.get('ALLOWED_BRANCHES', 'master,main').split(',')
LOG_FILE = os.environ.get('LOG_FILE', '/var/log/rereflect-webhook.log')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE) if os.path.exists(os.path.dirname(LOG_FILE)) else logging.StreamHandler(),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def verify_signature(payload: bytes, signature: str) -> bool:
    """Verify GitHub webhook signature."""
    if not signature:
        return False

    expected = 'sha256=' + hmac.new(
        SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Only handle /webhook endpoint
        if self.path != '/webhook':
            self.send_response(404)
            self.end_headers()
            return

        # Read payload
        content_length = int(self.headers.get('Content-Length', 0))
        payload = self.rfile.read(content_length)

        # Verify signature
        signature = self.headers.get('X-Hub-Signature-256', '')
        if not verify_signature(payload, signature):
            logger.warning(f"Invalid signature from {self.client_address[0]}")
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b'Invalid signature')
            return

        # Parse payload
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'Invalid JSON')
            return

        # Check event type
        event = self.headers.get('X-GitHub-Event', '')

        if event == 'ping':
            logger.info("Received ping from GitHub")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'pong')
            return

        if event != 'push':
            logger.info(f"Ignoring event: {event}")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(f'Ignored event: {event}'.encode())
            return

        # Check branch
        ref = data.get('ref', '')
        branch = ref.replace('refs/heads/', '')

        if branch not in ALLOWED_BRANCHES:
            logger.info(f"Ignoring push to branch: {branch}")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(f'Ignored branch: {branch}'.encode())
            return

        # Get commit info
        commit = data.get('head_commit', {})
        commit_msg = commit.get('message', 'No message')[:50]
        commit_author = commit.get('author', {}).get('name', 'Unknown')

        logger.info(f"Deploying: {branch} - {commit_msg} by {commit_author}")

        # Trigger deployment (async)
        try:
            subprocess.Popen(
                [DEPLOY_SCRIPT, branch],
                stdout=open('/var/log/rereflect-deploy.log', 'a'),
                stderr=subprocess.STDOUT,
                start_new_session=True
            )

            self.send_response(200)
            self.end_headers()
            self.wfile.write(f'Deployment triggered for {branch}'.encode())

        except Exception as e:
            logger.error(f"Failed to trigger deployment: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f'Deployment failed: {str(e)}'.encode())

    def do_GET(self):
        """Health check endpoint."""
        if self.path == '/health':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


def main():
    logger.info(f"Starting webhook server on port {PORT}")
    logger.info(f"Listening for pushes to branches: {ALLOWED_BRANCHES}")

    server = HTTPServer(('0.0.0.0', PORT), WebhookHandler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down webhook server")
        server.shutdown()


if __name__ == '__main__':
    main()
