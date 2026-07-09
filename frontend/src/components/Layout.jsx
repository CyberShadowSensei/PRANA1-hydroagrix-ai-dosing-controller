import React from 'react';
import { Outlet } from 'react-router-dom';
import NavBar from './NavBar';
import GlobalHUD from './GlobalHUD';
import { Toaster } from 'react-hot-toast';

const Layout = () => {
  return (
    <div className="flex h-screen w-full bg-slate-950 text-slate-200 overflow-hidden font-sans">
      {/* Side Navigation */}
      <NavBar />
      <Toaster position="bottom-right" toastOptions={{
        style: { background: '#1e293b', color: '#f8fafc', border: '1px solid #334155' }
      }}/>
      
      {/* Main Content Area */}
      <div className="flex-1 flex flex-col md:ml-[20vw] h-full overflow-hidden">
        {/* Persistent Global HUD at the top */}
        <GlobalHUD />
        
        {/* Scrollable Page Content */}
        <main className="flex-1 overflow-y-auto p-6 scroll-smooth bg-gradient-to-b from-slate-950 to-slate-900">
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default Layout;
