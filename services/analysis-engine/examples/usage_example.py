"""Example usage of the feedback analyzer."""
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analyzer import FeedbackAnalyzer, FeedbackInput


def main():
    """Run example analysis."""
    print("Customer Feedback Analyzer - Example Usage\n")
    print("=" * 60)

    # Load sample data
    sample_data_path = Path(__file__).parent / "sample_data.json"

    with open(sample_data_path, 'r') as f:
        data = json.load(f)

    # Create input model
    feedback_input = FeedbackInput(**data)

    print(f"\nAnalyzing {len(feedback_input.feedback)} feedback items...\n")

    # Initialize analyzer
    analyzer = FeedbackAnalyzer(
        enable_clustering=False,  # Set to True to enable topic clustering
        urgent_threshold=-0.7,
        very_negative_threshold=-0.5
    )

    # Perform analysis
    result = analyzer.analyze(feedback_input)

    # Display results
    print("ANALYSIS RESULTS")
    print("=" * 60)

    # Sentiment Summary
    print("\n📊 SENTIMENT SUMMARY")
    print("-" * 60)
    print(f"Positive: {result.sentiment_summary.positive_percent}%")
    print(f"Neutral:  {result.sentiment_summary.neutral_percent}%")
    print(f"Negative: {result.sentiment_summary.negative_percent}%")

    if result.sentiment_summary.trend_by_month:
        print("\n📈 Sentiment Trend by Month:")
        for month, trend in result.sentiment_summary.trend_by_month.items():
            print(f"  {month}: {trend.negative_percent}% negative (avg: {trend.avg_score:.2f})")

    # Pain Points
    print("\n🚨 COMMON PAIN POINTS")
    print("-" * 60)
    for i, pain_point in enumerate(result.common_pain_points[:5], 1):
        print(f"\n{i}. {pain_point.issue}")
        print(f"   Mentions: {pain_point.count}")
        if pain_point.examples:
            print(f"   Example: \"{pain_point.examples[0][:80]}...\"")

    # Feature Requests
    print("\n💡 TOP FEATURE REQUESTS")
    print("-" * 60)
    for i, request in enumerate(result.feature_requests[:5], 1):
        print(f"\n{i}. {request.feature}")
        print(f"   Requests: {request.count}")
        if request.examples:
            print(f"   Example: \"{request.examples[0][:80]}...\"")

    # Urgent Feedback
    print("\n⚠️  URGENT FEEDBACK")
    print("-" * 60)
    for i, urgent in enumerate(result.urgent_feedback[:5], 1):
        print(f"\n{i}. ID: {urgent.id}")
        print(f"   Issue: {urgent.issue}")
        print(f"   Reason: {urgent.reason}")
        print(f"   Sentiment: {urgent.sentiment}")

    # Topic Clusters
    if result.topic_clusters:
        print("\n🏷️  TOPIC CLUSTERS")
        print("-" * 60)
        for i, cluster in enumerate(result.topic_clusters[:5], 1):
            print(f"\n{i}. {cluster.topic}")
            print(f"   Count: {cluster.count}")
            if cluster.keywords:
                print(f"   Keywords: {', '.join(cluster.keywords)}")

    # Analysis Notes
    if result.analysis_notes:
        print(f"\n📝 Note: {result.analysis_notes}")

    print("\n" + "=" * 60)

    # Save results to JSON
    output_path = Path(__file__).parent / "analysis_output.json"
    with open(output_path, 'w') as f:
        json.dump(result.model_dump(), f, indent=2)

    print(f"\n✅ Full analysis saved to: {output_path}")


if __name__ == "__main__":
    main()
