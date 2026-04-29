import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const USER = process.env.DASHBOARD_BASIC_AUTH_USER;
const PASSWORD = process.env.DASHBOARD_BASIC_AUTH_PASSWORD;
const EXTRA_USERS = process.env.DASHBOARD_BASIC_AUTH_EXTRA_USERS;

function validCredentials(user: string, password: string) {
  if (USER && PASSWORD && user === USER && password === PASSWORD) return true;

  return (EXTRA_USERS ?? "")
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean)
    .some((entry) => {
      const sep = entry.indexOf(":");
      if (sep < 1) return false;
      return user === entry.slice(0, sep) && password === entry.slice(sep + 1);
    });
}

export function proxy(request: NextRequest) {
  if ((!USER || !PASSWORD) && !EXTRA_USERS) return NextResponse.next();

  const auth = request.headers.get("authorization");
  if (auth?.startsWith("Basic ")) {
    const decoded = atob(auth.slice(6));
    const sep = decoded.indexOf(":");
    if (sep >= 0 && validCredentials(decoded.slice(0, sep), decoded.slice(sep + 1))) return NextResponse.next();
  }

  return new NextResponse("Authentication required", {
    status: 401,
    headers: {
      "WWW-Authenticate": 'Basic realm="Prop Desk Dashboard"',
    },
  });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
