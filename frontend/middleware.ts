import { NextResponse } from "next/server";

import { auth } from "./auth";

export default auth((req) => {
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

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"]
};
