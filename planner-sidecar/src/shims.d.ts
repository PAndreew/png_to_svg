declare module "node:http" {
  export const createServer: any;
  export type IncomingMessage = any;
  export type ServerResponse = any;
}

declare module "@sinclair/typebox" {
  export const Type: any;
  export type Static<T = any> = any;
  export type TSchema = any;
}

declare module "@mariozechner/pi-agent-core" {
  export type AgentTool<TParameters = any, TDetails = any> = any;
}

declare const process: any;
declare const Buffer: any;
