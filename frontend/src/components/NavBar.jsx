/**
 * NavBar Component
 * Main responsive navigation bar with real-time connection status indicator.
 */
import React, { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { HiExternalLink, HiMenu, HiX } from "react-icons/hi";

// Use absolute path for public assets
const logoImage = '/images/logo.jpg';

const NavBar = () => {
  const [isOpen, setIsOpen] = useState(false);
  const toggleMenu = () => {
    setIsOpen(!isOpen);
  };


  const navigationLinks = [
    { to: "/dashboard", text: "Dashboard" },
    { to: "/camera", text: "Camera" },
    { to: "/temp", text: "Temp & Humidity" },
    { to: "/tds", text: "EC" },
    { to: "/ph", text: "PH Level" },
    { to: "/history", text: "Sensor Report" },
    { to: "/pump", text: "Pump" },
    { to: "/plant-presets", text: "Plant Presets" },
    { to: "/settings", text: "Settings" }
  ];

  return (
    <>
      {/* Mobile Header */}
      <div className="md:hidden fixed top-0 left-0 w-full bg-slate-800 border-b border-slate-700/30 z-30 px-4 py-2 flex justify-between items-center">
        <div className="flex items-center">
          <div
            className="h-9 w-10 bg-slate-800 flex items-center justify-center"
          >
            <img src={logoImage} alt="Hydroagrixai Logo" className="h-full object-contain" />
          </div>
        </div>
        <div className="flex items-center space-x-4">
          <button
            onClick={toggleMenu}
            className="text-slate-200 hover:text-white p-2"
            aria-label="Toggle navigation menu"
            aria-expanded={isOpen}
            aria-controls="mobile-menu"
          >
            {isOpen ? (
              <HiX className="h-6 w-6" />
            ) : (
              <HiMenu className="h-6 w-6" />
            )}
          </button>
        </div>
      </div>

      {/* Main Navigation */}
      <div id="mobile-menu" className={`fixed top-0 left-0 h-full flex flex-col items-center bg-gradient-to-b from-slate-800 to-slate-900 w-full md:w-[20vw] md:min-w-[250px] border-r border-slate-700/30 shadow-lg z-20 overflow-y-auto transition-transform duration-300 ${isOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        }`}>
        {/* Logo */}
        <div className="w-full text-center p-6 border-b border-slate-700/30 hidden md:block">
          <div className="h-12 w-auto mx-auto bg-slate-800 flex items-center justify-center">
            <img src={logoImage} alt="Hydroagrixai Logo" className="h-full object-contain" />
          </div>
        </div>

        {/* Navigation Links */}
        <div className="w-full px-4 py-8 flex md:flex-col flex-wrap justify-center gap-1 mt-4 md:mt-0">
          {navigationLinks.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              onClick={() => setIsOpen(false)}
              className={`w-full font-medium px-4 py-3 my-1 rounded-lg flex items-center transition-all duration-300 text-slate-200 hover:text-white hover:bg-slate-800/50 ${location.pathname === link.to ? 'bg-slate-800/50 text-white' : ''
                }`}
            >
              <HiExternalLink className="mr-3 text-xl text-slate-400" />
              {link.text}
            </Link>
          ))}
        </div>

        {/* Bottom decorative gradient */}
        <div className="mt-auto w-full h-px bg-gradient-to-r from-transparent via-slate-600/20 to-transparent"></div>
      </div>

      {/* Overlay for mobile */}
      {isOpen && (
        <div
          className="md:hidden fixed inset-0 bg-black/50 z-10"
          onClick={() => setIsOpen(false)}
        />
      )}
    </>
  );
};

export default NavBar;
