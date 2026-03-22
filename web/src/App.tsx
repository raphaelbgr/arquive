import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import { useTheme } from './hooks/useTheme';
import { Navbar } from './components/layout/Navbar';
import { Sidebar } from './components/layout/Sidebar';
import { FolderView } from './components/views/FolderView';
import { TimelineView } from './components/views/TimelineView';
import { LiveTVView } from './components/views/LiveTVView';
import { PeopleView } from './components/views/PeopleView';
import { DocumentsView } from './components/views/DocumentsView';
import { SettingsPanel } from './components/settings/SettingsPanel';
import { FileViewPage } from './components/views/FileViewPage';
import { LoginScreen } from './components/auth/LoginScreen';

function AppLayout({ children }: { children: React.ReactNode }) {
  // Initialize theme at the top of the component tree
  useTheme();
  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <Navbar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto">
          <AnimatePresence mode="wait">
            {children}
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginScreen />} />
        <Route
          path="/*"
          element={
            <AppLayout>
              <Routes>
                <Route path="/" element={<Navigate to="/browse" replace />} />
                <Route path="/browse" element={<FolderView />} />
                <Route path="/timeline" element={<TimelineView />} />
                <Route path="/documents" element={<DocumentsView />} />
                <Route path="/live" element={<LiveTVView />} />
                <Route path="/people" element={<PeopleView />} />
                <Route path="/settings" element={<SettingsPanel />} />
                <Route path="/view/:id" element={<FileViewPage />} />
              </Routes>
            </AppLayout>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
