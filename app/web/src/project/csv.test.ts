import { CsvError, parseCsv } from "./csv";

describe("parseCsv", () => {
  it("reads rows and fields, with no empty row for the final line break", () => {
    expect(parseCsv("field,description\nid,An identifier.\n")).toEqual([
      ["field", "description"],
      ["id", "An identifier."],
    ]);
  });

  it("reads CRLF line endings and a last line with none", () => {
    expect(parseCsv("a,b\r\n1,2")).toEqual([
      ["a", "b"],
      ["1", "2"],
    ]);
  });

  it("reads quoted fields holding commas, line breaks and doubled quotes", () => {
    expect(parseCsv('name,note\nsite,"North, upper\nslope"\nunit,"say ""mm"""\n')).toEqual([
      ["name", "note"],
      ["site", "North, upper\nslope"],
      ["unit", 'say "mm"'],
    ]);
  });

  it("keeps empty fields", () => {
    expect(parseCsv("a,,c\n,,\n")).toEqual([
      ["a", "", "c"],
      ["", "", ""],
    ]);
  });

  it("reads nothing from empty text", () => {
    expect(parseCsv("")).toEqual([]);
  });

  it("refuses a quoted field left open or followed by more text", () => {
    expect(() => parseCsv('a,"open\n')).toThrow(CsvError);
    expect(() => parseCsv('"a"b,c\n')).toThrow(CsvError);
  });
});
