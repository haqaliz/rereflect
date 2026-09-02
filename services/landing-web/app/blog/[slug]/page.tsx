import Link from 'next/link';
import { ArrowRight, ArrowLeft, Calendar, Clock, User } from 'lucide-react';
import { getAllPosts, getPostBySlug, getRelatedPosts } from '@/lib/blog';
import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import Nav from '@/components/landing/Nav';
import Footer from '@/components/landing/Footer';
import SubpageCTA from '@/components/landing/SubpageCTA';

export function generateStaticParams() {
  return getAllPosts().map((post) => ({ slug: post.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
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

export default async function BlogPostPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const post = getPostBySlug(slug);

  if (!post) {
    notFound();
  }

  const relatedPosts = getRelatedPosts(slug);

  return (
    <>
      <Nav />
      <main>
        <div className="lp-page">
          <div className="lp-post-header">
            <span className="lp-fig">Article</span>
            <h1 className="lp-display-1 lp-page-hero-title">{post.title}</h1>
            <div className="lp-post-meta-row">
              <span className="lp-meta">
                <Calendar className="h-3.5 w-3.5" />
                {new Date(post.date).toLocaleDateString('en-US', {
                  month: 'long',
                  day: 'numeric',
                  year: 'numeric',
                })}
              </span>
              <span className="lp-meta">
                <Clock className="h-3.5 w-3.5" />
                {post.readTime}
              </span>
              <span className="lp-meta">
                <User className="h-3.5 w-3.5" />
                {post.author}
              </span>
              <div className="flex flex-wrap justify-center gap-2">
                {post.tags.map((tag) => (
                  <span key={tag} className="lp-tag">
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          </div>

          <article className="lp-prose">
            {post.sections.map((section, i) => (
              <section key={`${section.heading}-${i}`}>
                <h2>{section.heading}</h2>
                {section.content?.map((p, j) => <p key={`p-${j}`}>{p}</p>)}
                {section.listItems ? (
                  <ul>
                    {section.listItems.map((li, j) => (
                      <li key={`li-${j}`}>{li}</li>
                    ))}
                  </ul>
                ) : null}
                {section.content2?.map((p, j) => <p key={`p2-${j}`}>{p}</p>)}
                {section.table ? (
                  <table>
                    <thead>
                      <tr>
                        {section.table.headers.map((h) => (
                          <th key={h}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {section.table.rows.map((row, j) => (
                        <tr key={`r-${j}`}>
                          {row.map((cell) => (
                            <td key={cell}>{cell}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : null}
              </section>
            ))}

            <div className="pt-4">
              <Link href="/blog" className="lp-back-link">
                <ArrowLeft className="h-3.5 w-3.5" />
                All articles
              </Link>
            </div>
          </article>

          {relatedPosts.length > 0 && (
            <div className="lp-section-block">
              <div className="lp-section-head">
                <span className="lp-fig">Keep reading</span>
                <h2 className="lp-display-2 mt-6 text-raise">Related articles.</h2>
              </div>
              <div className="lp-tile-grid">
                {relatedPosts.map((related) => (
                  <Link key={related.slug} href={`/blog/${related.slug}`} className="lp-tile group">
                    <div className="flex flex-wrap gap-2">
                      {related.tags.map((tag) => (
                        <span key={tag} className="lp-tag">
                          {tag}
                        </span>
                      ))}
                    </div>
                    <h2 className="lp-tile-name">{related.title}</h2>
                    <p className="lp-tile-tagline line-clamp-3">{related.excerpt}</p>
                    <span className="lp-tile-link">
                      Read article
                      <ArrowRight className="h-3.5 w-3.5 transition-transform duration-300 group-hover:translate-x-1" />
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          )}

          <SubpageCTA />
        </div>
      </main>
      <Footer />
    </>
  );
}