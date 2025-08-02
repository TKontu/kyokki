"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { useState, useEffect } from "react";
import { ReactNode } from "react";
import { useWsStore } from "@/lib/wsStore";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());
  const { setIsConnected } = useWsStore();

  useEffect(() => {
    const wsUrl = (process.env.NEXT_PUBLIC_API_BASE_URL || "ws://localhost:8000/api")
      .replace("http", "ws") + "/ws/status";
    
    console.log("Connecting to WebSocket at:", wsUrl);
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log("WebSocket connected");
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      console.log("WebSocket message received:", event.data);
      queryClient.invalidateQueries({ queryKey: ["items"] });
    };

    ws.onclose = () => {
      console.log("WebSocket disconnected");
      setIsConnected(false);
    };

    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
      setIsConnected(false);
    };

    return () => {
      ws.close();
    };
  }, [queryClient, setIsConnected]);

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}