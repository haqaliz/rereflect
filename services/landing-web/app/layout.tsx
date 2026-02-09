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
  title: "Rereflect - AI-Powered Customer Feedback Analysis",
  description: "Transform customer feedback into actionable insights with AI-powered sentiment analysis, pain point detection, and feature request extraction. 98% accuracy, real-time processing.",
  keywords: ["customer feedback", "sentiment analysis", "AI analysis", "SaaS analytics", "feedback management", "customer insights"],
  openGraph: {
    title: "Rereflect - AI-Powered Customer Feedback Analysis",
    description: "Transform customer feedback into actionable insights with AI-powered sentiment analysis, pain point detection, and feature request extraction.",
    url: "https://rereflect.ca",
    siteName: "Rereflect",
    type: "website",
    images: [
      {
        url: "/images/logo.png",
        width: 1200,
        height: 630,
        alt: "Rereflect - Customer Feedback Analysis",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Rereflect - AI-Powered Customer Feedback Analysis",
    description: "Transform customer feedback into actionable insights with AI-powered sentiment analysis, pain point detection, and feature request extraction.",
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
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className={`${montserrat.variable} ${merriweather.variable} ${ubuntuMono.variable} antialiased font-sans`}>
        {children}
      </body>
    </html>
  );
}
