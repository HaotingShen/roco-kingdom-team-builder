import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import Footer from "./Footer";

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex">
      <Sidebar />
      <div className="flex-1 ml-sidebar min-w-0 flex flex-col">
        <Topbar />
        <main className="p-4 flex-1">{children}</main>
        <Footer />
      </div>
    </div>
  );
}