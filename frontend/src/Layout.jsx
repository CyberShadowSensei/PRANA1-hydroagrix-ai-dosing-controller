/**
 * Page Layout Wrapper
 * Provides consistent viewport padding, navigation hierarchy, and responsiveness.
 */
import React from 'react'
import PlantCamera from './components/PlantCamera'
// import LightControl from './components/LightControl'
import MoistureSensor from './components/MoistureSensor'
import Temperature from './components/Temperature'
import TDS from './components/TDS'
import Dashboard from './components/Dashboard'
import Pump from './components/Pump'
import './style.css'

const Layout = () => {
  return (
    <>
        <PlantCamera/>
        {/* <LightControl/> */}
        <MoistureSensor/>
        <Temperature/>
        <TDS/>
        <Dashboard/>
        <Pump/>
    </>
  )
}

export default Layout