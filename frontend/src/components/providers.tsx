"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { useState, useEffect } from "react";
import { ReactNode } from "react";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  useEffect(() => {
    const ws = new WebSocket("ws://localhost:8000/api/ws/status");

    ws.onopen = () => {
      console.log("WebSocket connected");
    };

    ws.onmessage = (event) => {
      console.log("WebSocket message received:", event.data);
      // When a message is received, invalidate the items query to refetch data
      queryClient.invalidateQueries({ queryKey: ["items"] });
    };

    ws.onclose = () => {
      console.log("WebSocket disconnected");
    };

    // Clean up the connection when the component unmounts
    return () => {
      ws.close();
    };
  }, [queryClient]);

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
