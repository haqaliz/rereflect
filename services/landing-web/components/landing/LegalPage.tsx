import Link from 'next/link';
import { ChevronLeft } from 'lucide-react';
import Nav from '@/components/landing/Nav';
import Footer from '@/components/landing/Footer';

export interface LegalSection {
  h2: string;
  paragraphs: string[];
  listItems?: string[];
}

interface LegalPageProps {
  title: string;
  updated: string;
  sections: LegalSection[];
}

export default function LegalPage({ title, updated, sections }: LegalPageProps) {
  return (
    <>
      <Nav />
      <main>
        <div className="lp-page">
          <div className="lp-page-hero">
            <span className="lp-section-eyebrow">Legal</span>
            <h1 className="lp-page-hero-title font-display">{title}</h1>
            <p className="lp-page-hero-sub">Last updated: {updated}</p>
          </div>

          <article className="lp-prose">
            {sections.map((section) => (
              <section key={section.h2}>
                <h2>{section.h2}</h2>
                {section.paragraphs.map((p) => (
                  <p key={p}>{p}</p>
                ))}
                {section.listItems ? (
                  <ul>
                    {section.listItems.map((li) => (
                      <li key={li}>{li}</li>
                    ))}
                  </ul>
                ) : null}
              </section>
            ))}

            <div className="pt-6">
              <Link href="/" className="lp-back-link">
                <ChevronLeft className="h-4 w-4" />
                Back to home
              </Link>
            </div>
          </article>
        </div>
      </main>
      <Footer />
    </>
  );
}