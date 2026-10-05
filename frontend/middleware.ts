import { NextResponse, type NextRequest, type NextFetchEvent } from "next/server";

import { auth } from "./auth";

const authenticatedMiddleware = auth((req, _event: NextFetchEvent) => {
  const isLoggedIn = Boolean(req.auth);
  const pathname = req.nextUrl.pathname;
  const isAuthRoute = pathname.startsWith("/api/auth");
  const isLoginPage = pathname === "/login";
  const isSignupPage = pathname === "/signup";
  const isPublicAsset =
    pathname.startsWith("/_next") ||
    pathname === "/favicon.ico" ||
    pathname.match(/\.(?:png|jpg|jpeg|svg|gif|webp|ico|css|js)$/);

  if (isAuthRoute || isPublicAsset) {
    return NextResponse.next();
  }

  if (!isLoggedIn && !isLoginPage && !isSignupPage) {
    return NextResponse.redirect(new URL("/login", req.nextUrl));
  }

  if (isLoggedIn && (isLoginPage || isSignupPage)) {
    return NextResponse.redirect(new URL("/", req.nextUrl));
  }

  return NextResponse.next();
});

// Lazy Auth.js config returns the wrapper asynchronously in the installed v5 beta.
export default async function middleware(request: NextRequest, event: NextFetchEvent) {
  const handler = await authenticatedMiddleware;
  return handler(request, event);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"]
};
