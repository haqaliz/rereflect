import type { Metadata } from "next";
import { Montserrat, Merriweather, Ubuntu_Mono } from "next/font/google";
import "./globals.css";

const montserrat = Montserrat({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const merriweather = Merriweather({
  subsets: ["latin"],
  weight: ["300", "400", "700", "900"],
  variable: "--font-serif",
  display: "swap",
});

const ubuntuMono = Ubuntu_Mono({
  subsets: ["latin"],
  weight: ["400", "700"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://rereflect.ca"),
  title: "Rereflect - Open-Source Customer Feedback Analysis",
  description: "Self-hosted, MIT-licensed AI feedback analysis. Sentiment, pain points, feature requests, churn prediction, and 6+ integrations — fully unlocked, no vendor lock-in. Bring your own LLM key or run free on VADER.",
  keywords: ["open source", "self-hosted", "customer feedback", "sentiment analysis", "AI analysis", "feedback management", "customer insights", "BYOK", "MIT license"],
  openGraph: {
    title: "Rereflect - Open-Source Customer Feedback Analysis",
    description: "Self-host Rereflect on your own infrastructure. Every feature unlocked, MIT licensed, no tiers, no seats, no vendor lock-in.",
    url: "https://rereflect.ca",
    siteName: "Rereflect",
    type: "website",
    images: [
      {
        url: "/images/logo.png",
        width: 1200,
        height: 630,
        alt: "Rereflect - Open-Source Customer Feedback Analysis",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Rereflect - Open-Source Customer Feedback Analysis",
    description: "Self-host Rereflect on your own infrastructure. Every feature unlocked, MIT licensed, no tiers, no seats, no vendor lock-in.",
    images: ["/images/logo.png"],
    creator: "@rereflectapp",
  },
};

// Inline script to prevent flash of unstyled content (FOUC)
// This runs synchronously before any CSS is applied
const themeInitScript = `
(function() {
  try {
    var theme = localStorage.getItem('theme') || 'system';
    var resolved = theme;
    if (theme === 'system') {
      resolved = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    document.documentElement.setAttribute('data-theme', resolved);
    if (resolved === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  } catch (e) {}
})();
`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Preconnect to font providers for faster loading */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className={`${montserrat.variable} ${merriweather.variable} ${ubuntuMono.variable} antialiased font-sans`}>
        {children}
      </body>
    </html>
  );
}
