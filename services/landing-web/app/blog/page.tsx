import Link from 'next/link';
import { ArrowRight, Calendar, Clock } from 'lucide-react';
import { getAllPosts } from '@/lib/blog';
import type { Metadata } from 'next';
import Nav from '@/components/landing/Nav';
import Footer from '@/components/landing/Footer';
import PageHero from '@/components/landing/PageHero';
import RevealGrid from '@/components/landing/RevealGrid';
import SubpageCTA from '@/components/landing/SubpageCTA';

export const metadata: Metadata = {
  title: 'Blog | Rereflect',
  description:
    'Insights on customer feedback analysis, sentiment detection, and product management for SaaS teams.',
  openGraph: {
    title: 'Blog | Rereflect',
    description:
      'Insights on customer feedback analysis, sentiment detection, and product management for SaaS teams.',
    url: 'https://rereflect.ca/blog',
  },
};

export default function BlogPage() {
  const posts = getAllPosts();

  return (
    <>
      <Nav />
      <main>
        <div className="lp-page">
          <PageHero
            eyebrow="Blog"
            title="Insights on"
            gradient="customer feedback"
            sub="Practical insights on customer feedback analysis, product management, and building better SaaS products."
          />

          <div className="lp-section-block">
            <RevealGrid>
              <div className="lp-tile-grid">
                {posts.map((post) => (
                  <Link key={post.slug} href={`/blog/${post.slug}`} className="lp-tile group">
                    <div className="flex flex-wrap gap-2">
                      {post.tags.map((tag) => (
                        <span key={tag} className="lp-tag">
                          {tag}
                        </span>
                      ))}
                    </div>
                    <h2 className="lp-tile-name">{post.title}</h2>
                    <p className="lp-tile-tagline line-clamp-3">{post.excerpt}</p>
                    <div className="lp-meta">
                      <span className="inline-flex items-center gap-1.5">
                        <Calendar className="h-3.5 w-3.5" />
                        {new Date(post.date).toLocaleDateString('en-US', {
                          month: 'long',
                          day: 'numeric',
                          year: 'numeric',
                        })}
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <Clock className="h-3.5 w-3.5" />
                        {post.readTime}
                      </span>
                    </div>
                    <span className="lp-tile-link">
                      Read article
                      <ArrowRight className="h-3 w-3" />
                    </span>
                  </Link>
                ))}
              </div>
            </RevealGrid>
          </div>

          <SubpageCTA />
        </div>
      </main>
      <Footer />
    </>
  );
}