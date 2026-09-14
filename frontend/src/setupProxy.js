const { createProxyMiddleware } = require("http-proxy-middleware");

const hostname = process.env.REACT_APP_BE_HOSTNAME || "localhost";

module.exports = function (app) {
  app.use(
    "/be",
    createProxyMiddleware({
      target: "http://" + hostname + ":4000",
      changeOrigin: true,
      pathRewrite: { "^/be": "" },
    })
  );
  // Same-origin /cards/ paths in plugins. Local webpack has no nginx, so
  // optionally proxy to a host that already serves /cards/.
  const cardsOrigin = process.env.REACT_APP_CARDS_ORIGIN;
  if (cardsOrigin) {
    app.use(
      "/cards",
      createProxyMiddleware({
        target: cardsOrigin,
        changeOrigin: true,
      })
    );
  }
};
