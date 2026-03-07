import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import Footer from "./Footer";
import BottomNav from "./BottomNav";

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex">
      <Sidebar />
      <div className="flex-1 lg:ml-sidebar min-w-0 flex flex-col pb-16 lg:pb-0">
        <Topbar />
        <main className="p-4 flex-1">{children}</main>
        <Footer />
      </div>
      <BottomNav />
    </div>
  );
}