import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// Public routes allowed on marketing domain (rereflect.ca)
const publicRoutes = ['/', '/login', '/signup', '/terms', '/privacy'];

// App routes that should only be on app subdomain
const appRoutes = ['/dashboard', '/feedbacks', '/pain-points', '/feature-requests', '/urgent-feedbacks', '/categories', '/settings'];

export function middleware(request: NextRequest) {
  const hostname = request.headers.get('host') || '';
  const pathname = request.nextUrl.pathname;

  // Determine which domain we're on
  const isMarketingDomain = hostname === 'rereflect.ca' || hostname === 'www.rereflect.ca';
  const isAppDomain = hostname.startsWith('app.');

  // Skip middleware for static files and API routes
  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/api') ||
    pathname.includes('.') // Static files like favicon, images
  ) {
    return NextResponse.next();
  }

  // On marketing domain (rereflect.ca)
  if (isMarketingDomain) {
    // Check if trying to access app routes
    const isAppRoute = appRoutes.some(route => pathname.startsWith(route));

    if (isAppRoute) {
      // Redirect to app subdomain
      const appUrl = new URL(pathname, 'https://app.rereflect.ca');
      appUrl.search = request.nextUrl.search;
      return NextResponse.redirect(appUrl);
    }
  }

  // On app domain (app.rereflect.ca)
  if (isAppDomain) {
    // If on landing page, redirect to dashboard
    if (pathname === '/') {
      return NextResponse.redirect(new URL('/dashboard', request.url));
    }

    // Allow login/signup on app domain for auth flow
    // but redirect terms/privacy to marketing domain
    if (pathname === '/terms' || pathname === '/privacy') {
      const marketingUrl = new URL(pathname, 'https://rereflect.ca');
      return NextResponse.redirect(marketingUrl);
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     */
    '/((?!_next/static|_next/image|favicon.ico).*)',
  ],
};
