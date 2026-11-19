import { OGL_STATEMENT, licenceOf, renderNotices, wheelLicence } from "../bundle/notices";
import { BundleError } from "../bundle/resolve";

const metadata = (...headers: string[]) =>
  [
    "Metadata-Version: 2.4",
    "Name: example",
    "Version: 1.0",
    ...headers,
    "",
    "License: not a header",
  ].join("\n");

describe("licenceOf", () => {
  it("takes License-Expression first", () => {
    expect(
      licenceOf(metadata("License: MIT License", "License-Expression: BSD-3-Clause")),
    ).toBe("BSD-3-Clause");
  });

  it("takes a one-line License when there is no expression", () => {
    expect(licenceOf(metadata("License: Apache License 2.0"))).toBe("Apache License 2.0");
  });

  it("takes the classifiers when License is the licence's text", () => {
    const text = "License: Copyright (c) 2021, someone\n        All rights reserved.";
    expect(
      licenceOf(
        metadata(
          text,
          "Classifier: License :: OSI Approved :: BSD License",
          "Classifier: License :: OSI Approved :: Apache Software License",
          "Classifier: Programming Language :: Python",
        ),
      ),
    ).toBe("BSD License or Apache Software License");
  });

  it("reads only the header block, not the description below it", () => {
    expect(licenceOf(metadata())).toBeUndefined();
  });
});

describe("wheelLicence", () => {
  it("names the licence files the wheel carries", () => {
    const licence = wheelLicence("example", "1.0", metadata("License-Expression: MIT"), [
      "example/__init__.py",
      "example-1.0.dist-info/licenses/LICENSE",
      "example-1.0.dist-info/licenses/NOTICE",
      "example-1.0.dist-info/METADATA",
    ]);
    expect(licence).toEqual({
      name: "example",
      version: "1.0",
      licence: "MIT",
      files: ["example-1.0.dist-info/licenses/LICENSE", "example-1.0.dist-info/licenses/NOTICE"],
    });
  });

  it("fails the build for a wheel that names no licence", () => {
    expect(() => wheelLicence("example", "1.0", metadata(), [])).toThrow(BundleError);
  });
});

describe("renderNotices", () => {
  const wheels = [
    { name: "opf-fido", version: "1.6.1", licence: "Apache License 2.0", files: ["L.txt"] },
    { name: "certifi", version: "2026.4.22", licence: "MPL-2.0", files: [] },
  ];
  const notices = renderNotices({ pyodide: "314.0.8", python: "3.14.2", wheels, pronom: "v109" });

  it("names every wheel with its licence and where its source is", () => {
    for (const w of wheels) {
      expect(notices).toContain(`https://pypi.org/project/${w.name}/${w.version}/`);
      expect(notices).toContain(w.licence);
    }
  });

  it("says where Pyodide's source is and gives the PRONOM attribution", () => {
    expect(notices).toContain("https://github.com/pyodide/pyodide/tree/314.0.8");
    expect(notices).toContain(OGL_STATEMENT);
    expect(notices).toContain("v109");
  });
});
