"""Example of using the API with requests."""
import json
import requests
from pathlib import Path


def main():
    """Example API usage."""
    # API endpoint
    BASE_URL = "http://localhost:8000"

    # Load sample data
    sample_data_path = Path(__file__).parent / "sample_data.json"

    with open(sample_data_path, 'r') as f:
        data = json.load(f)

    print("Customer Feedback Analyzer - API Example\n")
    print("=" * 60)

    # Health check
    print("\n1. Checking API health...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print("   ✅ API is healthy")
            print(f"   Response: {response.json()}")
        else:
            print(f"   ❌ Health check failed: {response.status_code}")
            return
    except requests.exceptions.ConnectionError:
        print("   ❌ Cannot connect to API. Make sure it's running:")
        print("   Run: python -m src.api.main")
        return

    # Full analysis
    print("\n2. Performing full analysis...")
    response = requests.post(
        f"{BASE_URL}/api/v1/analyze",
        json=data,
        headers={"Content-Type": "application/json"}
    )

    if response.status_code == 200:
        result = response.json()
        print("   ✅ Analysis completed successfully")

        print(f"\n   📊 Sentiment: {result['sentiment_summary']['negative_percent']}% negative")
        print(f"   🚨 Pain points identified: {len(result['common_pain_points'])}")
        print(f"   💡 Feature requests: {len(result['feature_requests'])}")
        print(f"   ⚠️  Urgent items: {len(result['urgent_feedback'])}")

        # Save full result
        output_path = Path(__file__).parent / "api_analysis_output.json"
        with open(output_path, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\n   💾 Full result saved to: {output_path}")
    else:
        print(f"   ❌ Analysis failed: {response.status_code}")
        print(f"   Error: {response.text}")

    # Quick analysis
    print("\n3. Performing quick analysis...")
    response = requests.post(
        f"{BASE_URL}/api/v1/analyze/quick",
        json=data,
        headers={"Content-Type": "application/json"}
    )

    if response.status_code == 200:
        result = response.json()
        print("   ✅ Quick analysis completed")
        print(f"\n   Summary:")
        print(f"   - Total feedback: {result['total_feedback']}")
        print(f"   - Sentiment: {result['sentiment']}")
        print(f"   - Top pain point: {result['top_pain_point']}")
        print(f"   - Top feature request: {result['top_feature_request']}")
    else:
        print(f"   ❌ Quick analysis failed: {response.status_code}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
