import { create } from 'zustand';

type WsState = {
  isConnected: boolean;
  setIsConnected: (isConnected: boolean) => void;
};

export const useWsStore = create<WsState>((set) => ({
  isConnected: false,
  setIsConnected: (isConnected) => set({ isConnected }),
}));
