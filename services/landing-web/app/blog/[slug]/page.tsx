import Link from 'next/link';
import { Logo } from '@rereflect/ui';
import { ArrowLeft, ArrowRight, Calendar, Clock, User } from 'lucide-react';
import { getAllPosts, getPostBySlug, getRelatedPosts } from '@/lib/blog';
import { Footer } from '@/components/landing/Footer';
import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? (process.env.NODE_ENV === 'development' ? 'http://localhost:3000' : 'https://app.rereflect.ca');

export function generateStaticParams() {
  return getAllPosts().map((post) => ({ slug: post.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const post = getPostBySlug(slug);
  if (!post) return {};
  return {
    title: post.seoTitle,
    description: post.seoDescription,
    openGraph: {
      title: post.seoTitle,
      description: post.seoDescription,
      url: `https://rereflect.ca/blog/${post.slug}`,
      type: 'article',
      publishedTime: post.date,
      authors: [post.author],
    },
    twitter: {
      card: 'summary_large_image',
      title: post.seoTitle,
      description: post.seoDescription,
    },
  };
}

export default async function BlogPostPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const post = getPostBySlug(slug);

  if (!post) {
    notFound();
  }

  const relatedPosts = getRelatedPosts(slug);

  return (
    <div className="min-h-screen bg-background">
      {/* Navigation */}
      <nav className="relative z-50 px-6 py-5 border-b border-border">
        <div className="max-w-7xl mx-auto flex justify-between items-center">
          <Link href="/" className="flex items-center gap-3 group">
            <div className="relative">
              <div className="absolute inset-0 bg-primary/20 blur-xl rounded-full scale-150 opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
              <Logo size="lg" className="relative" />
            </div>
            <span className="text-xl font-bold tracking-tight">
              <span className="text-muted-foreground">Re</span>
              <span className="text-foreground">reflect</span>
            </span>
          </Link>

          <div className="hidden md:flex items-center gap-8">
            <Link href="/#features" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
              Features
            </Link>
            <Link href="/#pricing" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
              Pricing
            </Link>
            <Link href="/integrations" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
              Integrations
            </Link>
            <Link href="/blog" className="text-sm font-medium text-foreground transition-colors">
              Blog
            </Link>
          </div>

          <div className="flex items-center gap-3">
            <a href={`${APP_URL}/login`}>
              <button className="px-4 py-2.5 text-sm font-medium text-foreground/80 hover:text-foreground transition-colors">
                Sign In
              </button>
            </a>
            <a href={`${APP_URL}/signup`}>
              <button className="group relative px-5 py-2.5 text-sm font-semibold text-primary-foreground rounded-xl overflow-hidden transition-all duration-300 hover:shadow-lg hover:shadow-primary/25 hover:scale-[1.02]">
                <div className="absolute inset-0 bg-gradient-to-r from-primary via-chart-5 to-primary bg-[length:200%_100%] animate-[shimmer_3s_ease-in-out_infinite]" />
                <span className="relative flex items-center gap-1.5">
                  Get Started
                  <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                </span>
              </button>
            </a>
          </div>
        </div>
      </nav>

      {/* Article */}
      <article className="relative z-10 py-12 md:py-20">
        <div className="max-w-3xl mx-auto px-6">
          {/* Back link */}
          <Link href="/blog" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors mb-8">
            <ArrowLeft className="w-4 h-4" />
            Back to Blog
          </Link>

          {/* Header */}
          <header className="mb-12">
            <h1 className="text-3xl md:text-4xl lg:text-5xl font-bold tracking-tight text-foreground mb-6 leading-[1.15]">
              {post.title}
            </h1>

            <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <User className="w-4 h-4" />
                {post.author}
              </span>
              <span className="flex items-center gap-1.5">
                <Calendar className="w-4 h-4" />
                {new Date(post.date).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
              </span>
              <span className="flex items-center gap-1.5">
                <Clock className="w-4 h-4" />
                {post.readTime}
              </span>
            </div>
          </header>

          {/* Content */}
          <div className="space-y-10">
            {post.sections.map((section, i) => (
              <section key={i}>
                <h2 className="text-2xl font-bold text-foreground mb-4">
                  {section.heading}
                </h2>

                {section.content.map((paragraph, j) => (
                  <p key={j} className="text-foreground/85 leading-[1.8] mb-4 text-[1.05rem]">
                    {paragraph}
                  </p>
                ))}

                {section.listItems && (
                  <ul className="space-y-3 my-6 ml-1">
                    {section.listItems.map((item, k) => {
                      const dashIndex = item.indexOf(' — ');
                      return (
                        <li key={k} className="flex gap-3 text-foreground/85 leading-[1.7]">
                          <span className="w-1.5 h-1.5 rounded-full bg-primary mt-2.5 shrink-0" />
                          <span>
                            {dashIndex > -1 ? (
                              <>
                                <strong className="text-foreground">{item.slice(0, dashIndex)}</strong>
                                {item.slice(dashIndex)}
                              </>
                            ) : (
                              item
                            )}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                )}

                {section.content2?.map((paragraph: string, j: number) => (
                  <p key={`c2-${j}`} className="text-foreground/85 leading-[1.8] mb-4 text-[1.05rem]">
                    {paragraph}
                  </p>
                ))}

                {section.table && (
                  <div className="my-8 overflow-x-auto">
                    <table className="w-full border-collapse">
                      <thead>
                        <tr className="border-b-2 border-border">
                          {section.table.headers.map((header, h) => (
                            <th key={h} className="text-left py-3 px-4 text-sm font-bold text-foreground">
                              {header}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {section.table.rows.map((row, r) => (
                          <tr key={r} className="border-b border-border">
                            {row.map((cell, c) => (
                              <td key={c} className={`py-3 px-4 text-sm ${c === 0 ? 'font-medium text-foreground' : 'text-muted-foreground'}`}>
                                {cell}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            ))}
          </div>

          {/* Divider */}
          <div className="my-16 border-t border-border" />

          {/* CTA */}
          <div className="rounded-2xl bg-gradient-to-br from-primary/10 via-chart-5/10 to-accent/10 border border-primary/20 p-8 md:p-10 text-center">
            <h3 className="text-2xl font-bold text-foreground mb-3">
              Ready to organize your feedback?
            </h3>
            <p className="text-muted-foreground mb-6 max-w-lg mx-auto">
              Rereflect automatically analyzes customer feedback with AI-powered sentiment analysis, pain point detection, and urgency flagging.
            </p>
            <a href={`${APP_URL}/signup`}>
              <button className="group px-8 py-3.5 text-base font-semibold text-primary-foreground bg-gradient-to-r from-primary to-chart-5 rounded-2xl transition-all duration-300 hover:shadow-xl hover:shadow-primary/25 hover:scale-[1.02]">
                <span className="flex items-center justify-center gap-2">
                  Try Rereflect Free
                  <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                </span>
              </button>
            </a>
          </div>

          {/* Related Posts */}
          {relatedPosts.length > 0 && (
            <div className="mt-16">
              <h3 className="text-xl font-bold text-foreground mb-6">Continue reading</h3>
              <div className="space-y-4">
                {relatedPosts.map((related) => (
                  <Link
                    key={related.slug}
                    href={`/blog/${related.slug}`}
                    className="group block bg-card rounded-2xl border border-border p-6 transition-all duration-300 hover:shadow-lg hover:border-primary/30"
                  >
                    <h4 className="text-lg font-bold text-foreground group-hover:text-primary transition-colors mb-2">
                      {related.title}
                    </h4>
                    <p className="text-sm text-muted-foreground line-clamp-2">{related.excerpt}</p>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      </article>

      {/* Footer */}
      <Footer />

    </div>
  );
}
