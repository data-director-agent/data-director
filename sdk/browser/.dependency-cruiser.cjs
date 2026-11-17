/** Architecture rules for src/, as app/web has (#1059). tests/architecture.test.ts plants a
 * violation of each rule and checks that it is reported. */
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
