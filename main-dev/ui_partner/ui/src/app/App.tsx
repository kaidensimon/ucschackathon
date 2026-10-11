import { Navigate, Route, Routes } from "react-router";
import { LaterPage } from "../components/frame/LaterPage";
import { Gallery } from "../gallery/Gallery";
import { Review } from "../review/Review";
import { ReviewBar } from "../review/ReviewBar";
import { ChatScreen } from "../screens/ChatScreen";
import { ChatPage } from "../screens/chat/ChatPage";
import { HistoryPage } from "../screens/history/HistoryPage";
import { SettingsPage } from "../screens/settings/SettingsPage";

function Placeholder() {
  return (
    <main data-testid="placeholder" className="p-12">
      <h1 className="text-title">Syndicate</h1>
      <p className="mt-2 text-muted">Setup placeholder.</p>
    </main>
  );
}

function NotBuilt() {
  return (
    <main className="p-12">
      <h1 className="text-title">Not built yet</h1>
      <p className="mt-2 text-muted">This screen arrives later in Phase 1.</p>
    </main>
  );
}

export function App() {
  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <ReviewBar />
      <div className="min-h-0 flex-1 overflow-auto">
        <Routes>
          <Route path="/" element={<Navigate to="/chat/new" replace />} />
          <Route path="/placeholder" element={<Placeholder />} />
          <Route path="/review" element={<Review />} />
          {/* the sample debate: Phase 1 mock screens */}
          <Route path="/sample/new" element={<ChatScreen fresh />} />
          <Route path="/sample/:fixture" element={<ChatScreen />} />
          {/* one owner, one model */}
          <Route path="/chat/new" element={<ChatPage />} />
          <Route path="/chat/:id" element={<ChatPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/gallery" element={<Gallery />} />
          <Route path="/later/:what" element={<LaterPage />} />
          <Route path="*" element={<NotBuilt />} />
        </Routes>
      </div>
    </div>
  );
}
