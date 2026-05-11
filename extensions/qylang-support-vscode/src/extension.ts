import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  TransportKind,
  Trace,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;

function getServerOptions(): ServerOptions {
  const config = vscode.workspace.getConfiguration("qylang");
  const qyPath = config.get<string>("path", "qy");
  const parts = qyPath.split(/\s+/);

  return {
    run: {
      command: parts[0],
      args: [...parts.slice(1), "lsp"],
      transport: TransportKind.stdio,
    },
    debug: {
      command: parts[0],
      args: [...parts.slice(1), "lsp"],
      transport: TransportKind.stdio,
    },
  };
}

function getClientOptions(): LanguageClientOptions {
  return {
    documentSelector: [{ scheme: "file", language: "qy" }],
    synchronize: {
      configurationSection: "qylang",
    },
  };
}

function createClient(): LanguageClient {
  return new LanguageClient(
    "qylang",
    "QyLang Language Server",
    getServerOptions(),
    getClientOptions(),
  );
}

export async function activate(context: vscode.ExtensionContext) {
  const traceConfig = vscode.workspace
    .getConfiguration("qylang")
    .get<string>("trace.server", "off");

  client = createClient();

  const traceValue =
    traceConfig === "verbose"
      ? Trace.Verbose
      : traceConfig === "messages"
        ? Trace.Messages
        : Trace.Off;
  client.setTrace(traceValue);

  context.subscriptions.push(
    vscode.commands.registerCommand("qylang.restartServer", async () => {
      if (client) {
        await client.stop();
      }
      client = createClient();
      client.start();
      vscode.window.showInformationMessage("QyLang Language Server restarted.");
    }),
  );

  await client.start();
}

export async function deactivate() {
  await client?.stop();
}
