import type { ProjectDocument } from "./api";
import {
  assessments,
  checksOf,
  deltas,
  hasMetadataRecord,
  newerVersion,
  newlyMet,
  nextSteps,
  readFairness,
  readyForDeposit,
  tallyOf,
  totalOf,
} from "./fairness";
import { LATEST_RUN, aReport, aRun, meeting } from "../test/fairness";

const RECORD = "01900000-0000-7000-8000-00000000000a";

function aRecord(versions: number): ProjectDocument {
  return {
    document_id: RECORD,
    document_kind: "metadata_record",
    versions: Array.from({ length: versions }, (_, n) => ({ version: n + 1 })),
  } as unknown as ProjectDocument;
}

describe("reading a FAIR report", () => {
  it("recognises a report by its payload's class and nothing else", () => {
    expect(readFairness(LATEST_RUN.payload)?.checks.length).toBeGreaterThan(0);
    expect(
      readFairness({ schema_class: "StandardsAdvice", checks: [] }),
    ).toBeNull();
    expect(readFairness(null)).toBeNull();
    expect(
      assessments([LATEST_RUN, { ...LATEST_RUN, payload: null }]),
    ).toHaveLength(1);
  });

  it("counts each principle as the report does, whole numbers whatever the wire sent", () => {
    const report = aReport();
    for (const principle of ["F", "A", "I", "R"] as const) {
      const tally = tallyOf(report, principle);
      expect(
        Number.isInteger(tally.met) && Number.isInteger(tally.assessed),
      ).toBe(true);
      expect(tally.met).toBeLessThanOrEqual(tally.assessed);
    }
    const total = totalOf(report);
    expect(total.met).toBe(
      report.checks.filter((c) => c.met && !c.after_deposit).length,
    );
  });

  it("lists a principle's checks met first, then to do, then left until deposit", () => {
    const order = checksOf(aReport(), "F").map((c) =>
      c.after_deposit ? 2 : c.met ? 0 : 1,
    );
    expect(order).toEqual([...order].sort());
  });

  it("names the next steps as unmet checks, in the report's order", () => {
    const report = aReport();
    expect(nextSteps(report).map((c) => c.check)).toEqual(report.next_steps);
    expect(nextSteps(report).every((c) => !c.met)).toBe(true);
  });
});

describe("what changed between reports", () => {
  it("finds the checks met since the report before, and the principles whose counts moved", () => {
    const before = aReport();
    const [first] = before.next_steps as [string];
    const after = meeting(before, first);
    expect(newlyMet(after, before).map((c) => c.check)).toEqual([first]);
    const moved = deltas(after, before);
    expect(moved).toHaveLength(1);
    expect(moved[0]?.after.met).toBe((moved[0]?.before.met ?? 0) + 1);
    expect(deltas(before, before)).toEqual([]);
  });

  it("with no report before, takes what the report says is newly met since approval", () => {
    const report = aReport();
    const flagged = {
      ...report,
      checks: report.checks.map((c, n) => ({
        ...c,
        newly_met: c.met && n === 0,
      })),
    };
    expect(newlyMet(flagged, null)).toHaveLength(1);
  });

  it("is ready for deposit checks only once every check a draft can meet is met", () => {
    let report = aReport();
    expect(readyForDeposit(report)).toBe(false);
    for (const check of report.checks.filter(
      (c) => !c.met && !c.after_deposit,
    )) {
      report = meeting(report, check.check);
    }
    expect(readyForDeposit(report)).toBe(true);
    expect(aRun(report, "2026-01-09T00:00:00Z").payload).toMatchObject({
      next_steps: [],
    });
  });
});

describe("whether the report is out of date", () => {
  it("names a newer version of the record than the one assessed", () => {
    const report = aReport({
      assessed_version: { document_id: RECORD, version: 1 },
    });
    expect(newerVersion(report, [aRecord(2)])).toBe(2);
    expect(newerVersion(report, [aRecord(1)])).toBeNull();
    expect(
      newerVersion(aReport({ assessed_version: null }), [aRecord(2)]),
    ).toBeNull();
  });

  it("says whether the project holds a metadata record at all", () => {
    expect(hasMetadataRecord([aRecord(1)])).toBe(true);
    expect(hasMetadataRecord([aRecord(0)])).toBe(false);
    expect(hasMetadataRecord([])).toBe(false);
  });
});
