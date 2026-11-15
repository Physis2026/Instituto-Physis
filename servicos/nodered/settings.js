// Node-RED do Sistema Physis: automações visuais. Login obrigatório (falha ao subir sem a senha).
// Segredos vêm de env/nodered.env (preparar.sh gera a senha e o hash bcrypt).
const hash = process.env.NODERED_ADMIN_HASH;
const segredo = process.env.NODERED_CREDENCIAIS_SEGREDO;
if (!hash || !segredo) {
    throw new Error("NODERED_ADMIN_HASH e NODERED_CREDENCIAIS_SEGREDO são obrigatórios (rode servicos/preparar.sh)");
}

module.exports = {
    uiPort: 1880,
    flowFile: "flows.json",
    flowFilePretty: true,
    userDir: "/data",
    credentialSecret: segredo,
    adminAuth: {
        type: "credentials",
        sessionExpiryTime: 43200,
        users: [{ username: process.env.NODERED_ADMIN_USUARIO || "physis", password: hash, permissions: "*" }]
    },
    // nós "http in": também com usuário e senha (o mesmo login), nunca abertos
    httpNodeAuth: { user: process.env.NODERED_ADMIN_USUARIO || "physis", pass: hash },
    httpNodeRoot: "/fluxos",
    httpNodeCors: false,
    functionExternalModules: false,
    exportGlobalContextKeys: false,
    diagnostics: { enabled: false, ui: false },
    telemetry: { enabled: false },
    externalModules: { autoInstall: false, palette: { allowInstall: true, allowUpload: false } },
    editorTheme: { projects: { enabled: false }, tours: false },
    logging: { console: { level: "info", metrics: false, audit: true } }
};
