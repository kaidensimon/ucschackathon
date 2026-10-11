// The History screen (#/history): the list inside the window's frame. The search is kept in
// the address (?q=), so the screen opens again the way it was left.
import { useCallback } from "react";
import { AppFrame } from "../../components/frame/AppFrame";
import { useUrlState } from "../../components/frame/hooks";
import { TopBar } from "../../components/frame/TopBar";
import { useShortcuts } from "../../components/frame/useShortcuts";
import { HistoryList } from "./HistoryList";

export function HistoryPage() {
  const [search, change] = useUrlState();
  useShortcuts((s) => {
    if (s.kind === "help") change({ help: "1" });
    else if (s.kind === "close") change({ help: null });
    else return false;
    return true;
  });
  const onQuery = useCallback((query: string) => change({ q: query || null }), [change]);
  return (
    <AppFrame top={<TopBar seats={[]} />}>
      <HistoryList initialQuery={search.get("q") ?? ""} onQuery={onQuery} />
    </AppFrame>
  );
}
