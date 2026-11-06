/** Architecture rules for src/. See "The app" spec (docs/specs/app.md). */
module.exports = {
  forbidden: [
    {
      name: "no-circular",
      severity: "error",
      comment: "A file must not depend on itself through other files.",
      from: {},
      to: { circular: true },
    },
  ],
  options: {
    doNotFollow: { path: "node_modules" },
    tsConfig: { fileName: "tsconfig.json" },
    exclude: { path: "\\.test\\.tsx?$" },
  },
};
