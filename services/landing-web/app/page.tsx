import type { Metadata } from 'next';
import Nav from '@/components/landing/Nav';
import Hero from '@/components/landing/Hero';
import LiveClassification from '@/components/landing/LiveClassification';
import Features from '@/components/landing/Features';
import FAQ from '@/components/landing/FAQ';
import CTA from '@/components/landing/CTA';
import Footer from '@/components/landing/Footer';

export const metadata: Metadata = {
  title: 'Rereflect - Open-Source Customer Feedback Analysis',
  description:
    'Self-hosted, MIT-licensed AI feedback analysis. Sentiment, pain points, feature requests, churn prediction, and integrations — fully unlocked, no vendor lock-in. Bring your own LLM key or run free on VADER.',
  openGraph: {
    title: 'Rereflect - Open-Source Customer Feedback Analysis',
    description:
      'Self-host Rereflect on your own infrastructure. Every feature unlocked, MIT licensed, no tiers, no seats, no vendor lock-in.',
    url: 'https://rereflect.ca',
    siteName: 'Rereflect',
    type: 'website',
  },
};

export default function Home() {
  return (
    <>
      <Nav />
      <main>
        <Hero />
        <LiveClassification />
        <Features />
        <FAQ />
        <CTA />
      </main>
      <Footer />
      <div className="lp-noise" aria-hidden="true" />
    </>
  );
}