#!/usr/bin/env python3
"""
GitHub Webhook Listener for Rereflect Auto-Deployment
Listens for push events on master branch and triggers deployment.
"""

import hashlib
import hmac
import json
import os
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

# Configuration
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', '')
DEPLOY_SCRIPT = '/opt/rereflect/deploy/deploy.sh'
LOG_FILE = '/opt/rereflect/deploy/deploy.log'
LISTEN_PORT = int(os.environ.get('WEBHOOK_PORT', 9000))
BRANCH = 'master'


def log(message: str):
    """Log message to file and stdout."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(log_line + '\n')
    except Exception as e:
        print(f"Failed to write to log: {e}")


def verify_signature(payload: bytes, signature: str) -> bool:
    """Verify GitHub webhook signature."""
    if not WEBHOOK_SECRET:
        log("WARNING: No WEBHOOK_SECRET set, skipping signature verification")
        return True

    if not signature:
        log("ERROR: No signature provided")
        return False

    try:
        sha_name, signature_hash = signature.split('=')
        if sha_name != 'sha256':
            log(f"ERROR: Unsupported hash algorithm: {sha_name}")
            return False

        mac = hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256)
        expected = mac.hexdigest()

        if not hmac.compare_digest(expected, signature_hash):
            log("ERROR: Signature mismatch")
            return False

        return True
    except Exception as e:
        log(f"ERROR: Signature verification failed: {e}")
        return False


def run_deploy():
    """Execute the deployment script."""
    log("Starting deployment...")
    try:
        result = subprocess.run(
            ['/bin/bash', DEPLOY_SCRIPT],
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )

        if result.returncode == 0:
            log("Deployment completed successfully")
            log(f"STDOUT: {result.stdout[-1000:] if len(result.stdout) > 1000 else result.stdout}")
        else:
            log(f"Deployment failed with exit code {result.returncode}")
            log(f"STDERR: {result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr}")

        return result.returncode == 0
    except subprocess.TimeoutExpired:
        log("ERROR: Deployment timed out after 10 minutes")
        return False
    except Exception as e:
        log(f"ERROR: Deployment failed: {e}")
        return False


class WebhookHandler(BaseHTTPRequestHandler):
    """Handle incoming GitHub webhooks."""

    def log_message(self, format, *args):
        """Override to use our logging."""
        log(f"HTTP: {args[0]}")

    def do_GET(self):
        """Health check endpoint."""
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "healthy", "service": "rereflect-webhook"}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        """Handle webhook POST requests."""
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
            self.send_response(403)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error": "Invalid signature"}')
            return

        # Parse payload
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            log(f"ERROR: Invalid JSON payload: {e}")
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error": "Invalid JSON"}')
            return

        # Check event type
        event = self.headers.get('X-GitHub-Event', '')
        log(f"Received event: {event}")

        if event == 'ping':
            log("Received ping event - webhook is configured correctly")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"message": "pong"}')
            return

        if event != 'push':
            log(f"Ignoring non-push event: {event}")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"message": "Event ignored"}')
            return

        # Check branch
        ref = data.get('ref', '')
        if ref != f'refs/heads/{BRANCH}':
            log(f"Ignoring push to non-master branch: {ref}")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"message": "Branch ignored"}')
            return

        # Log commit info
        commits = data.get('commits', [])
        pusher = data.get('pusher', {}).get('name', 'unknown')
        log(f"Push to {BRANCH} by {pusher} with {len(commits)} commit(s)")

        if commits:
            latest = commits[-1]
            log(f"Latest commit: {latest.get('id', '')[:8]} - {latest.get('message', '').split(chr(10))[0]}")

        # Respond immediately, deploy in background
        self.send_response(202)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"message": "Deployment triggered"}')

        # Run deployment (blocking - subsequent requests will queue)
        run_deploy()


def main():
    """Start the webhook server."""
    log(f"Starting webhook server on port {LISTEN_PORT}")
    log(f"Listening for pushes to {BRANCH} branch")
    log(f"Deploy script: {DEPLOY_SCRIPT}")

    if not WEBHOOK_SECRET:
        log("WARNING: WEBHOOK_SECRET not set - webhook signatures will not be verified!")

    server = HTTPServer(('0.0.0.0', LISTEN_PORT), WebhookHandler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Shutting down webhook server")
        server.shutdown()


if __name__ == '__main__':
    main()
