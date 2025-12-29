import { BarChart3, Brain, MessageSquare, TrendingUp, Zap, Shield } from 'lucide-react';
import Link from 'next/link';
import { Logo } from '@/components/Logo';

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50">
      {/* Hero Section */}
      <div className="relative overflow-hidden">
        <div className="absolute inset-0 bg-grid-pattern opacity-5" />

        <nav className="relative z-10 px-6 py-4">
          <div className="max-w-7xl mx-auto flex justify-between items-center">
            <div className="flex items-center space-x-2">
              <Logo size="lg" />
              <span className="text-xl font-bold text-gray-900">
                Rereflect
              </span>
            </div>
            <div className="flex items-center space-x-4">
              <Link href="/login">
                <button className="px-4 py-2 text-gray-700 hover:text-gray-900 font-medium transition">
                  Sign In
                </button>
              </Link>
              <Link href="/signup">
                <button className="px-6 py-2.5 bg-amber-500 text-white rounded-lg hover:bg-amber-600 hover:shadow-lg hover:scale-105 transition-all duration-200 font-medium">
                  Get Started
                </button>
              </Link>
            </div>
          </div>
        </nav>

        <div className="relative z-10 max-w-7xl mx-auto px-6 pt-20 pb-32">
          <div className="text-center">
            <div className="inline-flex items-center space-x-2 px-4 py-2 bg-amber-100 text-amber-700 rounded-full mb-6">
              <Zap className="w-4 h-4" />
              <span className="text-sm font-semibold">AI-Powered Feedback Analysis</span>
            </div>

            <h1 className="text-6xl md:text-7xl font-bold text-gray-900 mb-6 leading-tight">
              Transform Customer
              <br />
              <span className="text-amber-500">
                Feedback into Insights
              </span>
            </h1>

            <p className="text-xl text-gray-600 mb-10 max-w-2xl mx-auto">
              Automatically analyze sentiment, extract pain points, and discover feature requests
              from customer feedback using advanced AI technology.
            </p>

            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <Link href="/signup">
                <button className="px-8 py-4 bg-amber-500 text-white rounded-xl hover:bg-amber-600 hover:shadow-2xl hover:scale-105 transition-all duration-200 font-semibold text-lg">
                  Start Free Trial
                </button>
              </Link>
              <Link href="/login">
                <button className="px-8 py-4 bg-white text-gray-700 border-2 border-gray-300 rounded-xl hover:border-gray-400 hover:shadow-lg transition-all duration-200 font-semibold text-lg">
                  View Demo
                </button>
              </Link>
            </div>

            <div className="mt-12 flex items-center justify-center space-x-8 text-sm text-gray-500">
              <div className="flex items-center space-x-2">
                <Shield className="w-5 h-5 text-green-600" />
                <span>Secure & Private</span>
              </div>
              <div className="flex items-center space-x-2">
                <Zap className="w-5 h-5 text-amber-500" />
                <span>Real-time Analysis</span>
              </div>
              <div className="flex items-center space-x-2">
                <TrendingUp className="w-5 h-5 text-blue-600" />
                <span>Actionable Insights</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Features Section */}
      <div className="max-w-7xl mx-auto px-6 py-24">
        <div className="text-center mb-16">
          <h2 className="text-4xl font-bold text-gray-900 mb-4">
            Everything you need to understand your customers
          </h2>
          <p className="text-lg text-gray-600">
            Powerful features to help you make data-driven decisions
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-8">
          <div className="bg-white p-8 rounded-2xl shadow-lg hover:shadow-xl transition-shadow border border-gray-100">
            <div className="w-12 h-12 bg-amber-500 rounded-xl flex items-center justify-center mb-4">
              <MessageSquare className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-xl font-semibold text-gray-900 mb-3">Sentiment Analysis</h3>
            <p className="text-gray-600">
              Automatically detect positive, neutral, and negative sentiment in customer feedback
              with high accuracy using advanced NLP.
            </p>
          </div>

          <div className="bg-white p-8 rounded-2xl shadow-lg hover:shadow-xl transition-shadow border border-gray-100">
            <div className="w-12 h-12 bg-amber-600 rounded-xl flex items-center justify-center mb-4">
              <Brain className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-xl font-semibold text-gray-900 mb-3">Smart Extraction</h3>
            <p className="text-gray-600">
              Extract pain points, feature requests, and urgent issues automatically from
              unstructured feedback data.
            </p>
          </div>

          <div className="bg-white p-8 rounded-2xl shadow-lg hover:shadow-xl transition-shadow border border-gray-100">
            <div className="w-12 h-12 bg-amber-400 rounded-xl flex items-center justify-center mb-4">
              <BarChart3 className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-xl font-semibold text-gray-900 mb-3">Visual Analytics</h3>
            <p className="text-gray-600">
              Beautiful dashboards and reports that make it easy to understand trends
              and make informed decisions.
            </p>
          </div>
        </div>
      </div>

      {/* CTA Section */}
      <div className="bg-amber-500 py-20">
        <div className="max-w-4xl mx-auto text-center px-6">
          <h2 className="text-4xl font-bold text-white mb-6">
            Ready to transform your feedback?
          </h2>
          <p className="text-xl text-amber-100 mb-8">
            Join companies that are already making better decisions with AI-powered insights.
          </p>
          <Link href="/signup">
            <button className="px-8 py-4 bg-white text-amber-600 rounded-xl hover:shadow-2xl hover:scale-105 transition-all duration-200 font-semibold text-lg">
              Start Your Free Trial
            </button>
          </Link>
        </div>
      </div>

      {/* Footer */}
      <footer className="bg-gray-900 text-gray-400 py-12">
        <div className="max-w-7xl mx-auto px-6 text-center">
          <div className="flex items-center justify-center space-x-2 mb-4">
            <Logo size="md" />
            <span className="text-lg font-bold text-white">Rereflect</span>
          </div>
          <p className="text-sm">
            © 2025 Rereflect. All rights reserved. Built with care for better customer understanding.
          </p>
        </div>
      </footer>
    </div>
  );
}
