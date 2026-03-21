import { Elysia } from "elysia";

const app = new Elysia().get("/", () => "Hello Elysia").listen(3000);

app.get("/health", () => new Response("ok", { status: 200 }));

console.log(
  `🦊 Elysia is running at ${app.server?.hostname}:${app.server?.port}`,
  `Env var: ${process.env.TEST!}`,
);
