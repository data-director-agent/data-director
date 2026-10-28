import { render } from "@testing-library/react";

import type { Shape } from "../../../run/schema";
import { Scalar } from "./Scalar";

const TEXT: Shape = { kind: "scalar", type: "string" };
const CHOICE: Shape = { kind: "scalar", type: "string", options: ["not_applicable"] };

function text(value: unknown, shape: Shape = TEXT) {
  return render(<Scalar value={value} shape={shape} />).container;
}

describe("Scalar", () => {
  it.each([
    [3, TEXT, "3"],
    [0.12345, TEXT, "0.12"],
    [true, TEXT, "Yes"],
    [false, TEXT, "No"],
    ["not_applicable", CHOICE, "not applicable"],
    ["keep_this", TEXT, "keep_this"],
    [["a", 2], TEXT, "a, 2"],
  ])("writes %j as %s", (value, shape, expected) => {
    expect(text(value, shape)).toHaveTextContent(expected);
  });

  it("shows an object as code", () => {
    expect(text({ a: 1 }).querySelector("code")).toHaveTextContent('{"a":1}');
  });
});
