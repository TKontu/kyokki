"use client";

import { useWsStore } from "@/lib/wsStore";

export function WsStatusIndicator() {
  const { isConnected } = useWsStore();

  return (
    <div className="fixed bottom-4 right-4 flex items-center space-x-2 p-2 bg-white rounded-full shadow-lg">
      <div
        className={`w-3 h-3 rounded-full ${
          isConnected ? "bg-green-500" : "bg-red-500"
        }`}
      />
      <span className="text-sm font-medium text-gray-700">
        {isConnected ? "Connected" : "Disconnected"}
      </span>
    </div>
  );
}
