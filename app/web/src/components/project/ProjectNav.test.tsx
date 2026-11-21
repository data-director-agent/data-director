import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";

import { ProjectNav } from "./ProjectNav";

describe("ProjectNav", () => {
  it("places the project under Projects and links its pages, marking the one shown", async () => {
    const { container } = render(<ProjectNav projectId="p 1" name="Moorland" current="journey" />);
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumbs).getByRole("link", { name: "Projects" })).toHaveAttribute(
      "href",
      "/projects",
    );
    expect(within(crumbs).getByText("Moorland")).toBeInTheDocument();

    const tabs = screen.getByRole("navigation", { name: "Project" });
    const documents = within(tabs).getByRole("link", { name: "Documents" });
    const map = within(tabs).getByRole("link", { name: "Journey map" });
    expect(documents).toHaveAttribute("href", "/projects/p%201");
    expect(documents).not.toHaveAttribute("aria-current");
    expect(map).toHaveAttribute("href", "/projects/p%201/journey");
    expect(map).toHaveAttribute("aria-current", "page");
    expect(within(tabs).getByRole("link", { name: "Conversations" })).toHaveAttribute("href", "/");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("gives each of the project's panels a tab of its own", () => {
    render(<ProjectNav projectId="p 1" name="Moorland" current="repository" />);
    const tabs = screen.getByRole("navigation", { name: "Project" });
    const paths = {
      Researchers: "/projects/p%201/researchers",
      Members: "/projects/p%201/members",
      "Project facts": "/projects/p%201/facts",
      Repository: "/projects/p%201/repository",
      "Use of generative AI": "/projects/p%201/ai-use",
      "Deposit package": "/projects/p%201/deposit",
    };
    for (const [name, href] of Object.entries(paths)) {
      expect(within(tabs).getByRole("link", { name })).toHaveAttribute("href", href);
    }
    expect(within(tabs).getByRole("link", { name: "Repository" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("marks Documents on the documents page, and names the project generically until known", () => {
    render(<ProjectNav projectId="p" name={null} current="documents" />);
    expect(screen.getByText("This project")).toBeInTheDocument();
    const tabs = screen.getByRole("navigation", { name: "Project" });
    expect(within(tabs).getByRole("link", { name: "Documents" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});
