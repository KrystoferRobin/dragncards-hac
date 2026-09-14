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
  // borrow toybox (or REACT_APP_CARDS_ORIGIN) for art.
  app.use(
    "/cards",
    createProxyMiddleware({
      target: process.env.REACT_APP_CARDS_ORIGIN || "https://toybox.hundredacre.club",
      changeOrigin: true,
    })
  );
};
