import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Admin from "@/components/admin";
import Market from "@/components/market";
import "./globals.css";

// Prices change when a scrape finishes (hours apart), so a fetched result stays fresh for a minute
// and is kept for five, and switching filters back and forth does not hit the API again.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      gcTime: 5 * 60_000,
      retry: 1,
      retryDelay: 500,
      refetchOnWindowFocus: false,
      networkMode: "always", // try even when offline, so the UI shows the error instead of waiting forever
    },
  },
});

function Page() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  if (path === "/admin") return <Admin />;
  return <Market demo={path === "/demo"} />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <Page />
    </QueryClientProvider>
  </StrictMode>,
);
