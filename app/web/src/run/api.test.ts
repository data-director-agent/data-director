import { nextCursor } from "./api";

describe("nextCursor", () => {
  it("reads the next page's cursor from a Link header", () => {
    expect(nextCursor('<http://host/api/runs?limit=50&before=abc-1>; rel="next"')).toBe("abc-1");
    expect(nextCursor('</api/runs?before=x>; rel="prev", </api/runs?before=y>; rel="next"')).toBe(
      "y",
    );
  });

  it("finds none on the last page", () => {
    expect(nextCursor(null)).toBeNull();
    expect(nextCursor('</api/runs?before=x>; rel="prev"')).toBeNull();
  });
});
