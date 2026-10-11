import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { sampleView } from "../../gallery/entry";
import { SeatSheet } from "./SeatSheet";
import { TableView } from "./TableView";

afterEach(cleanup);

describe("SeatSheet", () => {
  it("shows nothing while no seat is chosen", () => {
    render(<SeatSheet view={sampleView("lease", "debating")} seatId={null} onClose={() => {}} />);
    expect(document.querySelector("[data-part=seat-sheet]")).toBeNull();
  });

  it("names the seat, its model, its place, its state and its last vote", () => {
    render(<SeatSheet view={sampleView("lease", "vote")} seatId="s4" onClose={() => {}} />);
    const sheet = screen.getByRole("dialog", { name: "Gemma" });
    expect(sheet.getAttribute("data-part")).toBe("seat-sheet");
    const head = within(sheet).getByRole("banner");
    expect(head.textContent).toContain("Gemma example model");
    expect(head.textContent).toContain("Seat 4");
    expect(head.textContent).toContain("Waiting");
    expect(head.textContent).toContain("Agreed at the last vote");
    expect(head.querySelectorAll("[data-part=vote-mark]")).toHaveLength(1);
  });

  it("lists every turn of that seat, newest last, with who it spoke to, the time and what it cited", () => {
    const view = sampleView("lease", "debating");
    render(<SeatSheet view={view} seatId="s4" onClose={() => {}} />);
    const sheet = screen.getByRole("dialog");
    const turns = [...sheet.querySelectorAll("[data-part=sheet-turn]")];
    const mine = view.turns.filter((t) => t.seatId === "s4");
    expect(turns).toHaveLength(mine.length);
    expect(turns.length).toBeGreaterThanOrEqual(2);
    turns.forEach((el, i) => {
      expect(el.textContent).toContain(mine[i]?.text);
    });
    expect(turns[0]?.textContent).toContain("Reading your files");
    expect(turns[1]?.textContent).toContain("Round 1");
    expect(turns[1]?.textContent).toContain("to all");
    expect(turns[1]?.textContent).toContain("0:51");
    expect(turns[1]?.querySelectorAll("[data-part=citation-chip]")).toHaveLength(2);
    expect(turns[1]?.textContent).toContain("Renewal letter 2026.pdf, page 1");
    const read = within(sheet).getByRole("region", { name: "Read" });
    expect(read.textContent).toContain("Renewal letter 2026.pdf");
    expect(read.textContent).toContain("House rules.docx");
  });

  it("says so when the seat has said nothing", () => {
    render(<SeatSheet view={sampleView("lease", "spooling")} seatId="s1" onClose={() => {}} />);
    const sheet = screen.getByRole("dialog");
    expect(sheet.textContent).toContain("Nothing yet.");
    expect(within(sheet).queryByRole("region", { name: "Read" })).toBeNull();
  });

  it("closes on Esc and on Close", () => {
    const onClose = vi.fn();
    render(<SeatSheet view={sampleView("lease", "debating")} seatId="s4" onClose={onClose} />);
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("gives focus back to the seat at the table when it closes", async () => {
    function Both() {
      const view = sampleView("lease", "debating");
      const [seatId, setSeatId] = useState<string | null>(null);
      return (
        <>
          <TableView view={view} width={1040} height={558} onOpenSeat={setSeatId} />
          <SeatSheet view={view} seatId={seatId} onClose={() => setSeatId(null)} />
          {/* stands in for the 1 to 7 keys: opens a seat without touching its button */}
          <button type="button" onClick={() => setSeatId("s2")}>
            open Llama
          </button>
        </>
      );
    }
    render(<Both />);
    fireEvent.click(screen.getByRole("button", { name: "open Llama", hidden: true }));
    expect(screen.getByRole("dialog", { name: "Llama" })).toBeTruthy();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(document.activeElement?.getAttribute("data-seat-id")).toBe("s2"));
  });
});
