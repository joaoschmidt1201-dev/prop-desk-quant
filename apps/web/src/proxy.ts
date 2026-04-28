import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const USER = process.env.DASHBOARD_BASIC_AUTH_USER;
const PASSWORD = process.env.DASHBOARD_BASIC_AUTH_PASSWORD;

export function proxy(request: NextRequest) {
  if (!USER || !PASSWORD) return NextResponse.next();

  const auth = request.headers.get("authorization");
  if (auth?.startsWith("Basic ")) {
    const [user, password] = atob(auth.slice(6)).split(":");
    if (user === USER && password === PASSWORD) return NextResponse.next();
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
