--[[
    AutomaticMapper_UI.lua
    Interfaz visual en el juego para AutomaticMapper (Project Zomboid Build 42)
--]]

require "ISUI/ISCollapsableWindow"
require "ISUI/ISButton"
require "ISUI/ISTextEntryBox"
require "ISUI/ISComboBox"
require "ISUI/ISTickBox"
require "ISUI/ISLabel"
require "AutomaticMapper_Shared"
require "AutomaticMapper/AutomaticMapper_Core"

AutomaticMapperUI = ISCollapsableWindow:derive("AutomaticMapperUI")

function AutomaticMapperUI:new(x, y, width, height)
    local o = ISCollapsableWindow:new(x, y, width, height)
    setmetatable(o, self)
    self.__index = self
    o.title = "AutomaticMapper — Knox Spatial Extractor"
    o.resizable = false
    o.selectedPreset = "Todo Knox"
    return o
end

function AutomaticMapperUI:initialise()
    ISCollapsableWindow.initialise(self)
end

function AutomaticMapperUI:createChildren()
    ISCollapsableWindow.createChildren(self)

    local padX = 20
    local curY = 32

    -- Titulo / Descripcion
    local lblTitle = ISLabel:new(padX, curY, 20, "Selector de Coordenadas y Filtros:", 1, 1, 1, 1, UIFont.Medium, true)
    self:addChild(lblTitle)
    curY = curY + 26

    -- Selector de Localidad
    local lblCombo = ISLabel:new(padX, curY, 20, "Presintonía de Localidad:", 0.8, 0.8, 0.8, 1, UIFont.Small, true)
    self:addChild(lblCombo)
    
    self.comboPresets = ISComboBox:new(padX + 160, curY - 2, 190, 22, self, self.onSelectPreset)
    self:addChild(self.comboPresets)
    
    for townName, _ in pairs(AutomaticMapper.TownPresets) do
        self.comboPresets:addOption(townName)
    end
    self.comboPresets.selected = 1
    curY = curY + 32

    -- Cajas de Coordenadas
    local lblCoords = ISLabel:new(padX, curY, 20, "Límites Manuales (MinX, MinY, MaxX, MaxY):", 0.8, 0.8, 0.8, 1, UIFont.Small, true)
    self:addChild(lblCoords)
    curY = curY + 20

    local boxWidth = 75
    self.txtMinX = ISTextEntryBox:new("0", padX, curY, boxWidth, 22)
    self.txtMinY = ISTextEntryBox:new("0", padX + 85, curY, boxWidth, 22)
    self.txtMaxX = ISTextEntryBox:new("30000", padX + 170, curY, boxWidth, 22)
    self.txtMaxY = ISTextEntryBox:new("30000", padX + 255, curY, boxWidth, 22)
    
    self:addChild(self.txtMinX)
    self:addChild(self.txtMinY)
    self:addChild(self.txtMaxX)
    self:addChild(self.txtMaxY)
    curY = curY + 34

    -- Opciones ampliadas requeridas por el usuario
    self.tickOptions = ISTickBox:new(padX, curY, 340, 20, "", self, self.onTick)
    self:addChild(self.tickOptions)
    
    self.optIgnoreWild   = self.tickOptions:addOption("Ignorar bosques de relleno (compactar envolvente)")
    self.optObjects      = self.tickOptions:addOption("Incluir objetos (alcantarillas, contenedores, muebles)")
    self.optNearbyRoads  = self.tickOptions:addOption("Incluir rutas y carreteras cercanas")
    self.optNearbyBlds   = self.tickOptions:addOption("Incluir casas y edificios cercanos")
    self.optRooms        = self.tickOptions:addOption("Extraer habitaciones y rectángulos interiores")
    
    self.tickOptions:setSelected(self.optIgnoreWild, true)
    self.tickOptions:setSelected(self.optObjects, true)
    self.tickOptions:setSelected(self.optNearbyRoads, true)
    self.tickOptions:setSelected(self.optNearbyBlds, true)
    self.tickOptions:setSelected(self.optRooms, true)
    curY = curY + 120

    -- Radio de proximidad
    local lblRadius = ISLabel:new(padX, curY, 20, "Radio de proximidad (tiles):", 0.8, 0.8, 0.8, 1, UIFont.Small, true)
    self:addChild(lblRadius)
    self.txtRadius = ISTextEntryBox:new("35", padX + 190, curY - 2, 60, 22)
    self:addChild(self.txtRadius)
    curY = curY + 32

    -- Boton de Accion
    self.btnScan = ISButton:new(padX, curY, 330, 32, "INICIAR ESCANEO Y EXPORTAR", self, self.onStartScan)
    self.btnScan.backgroundColor = { r = 0.15, g = 0.55, b = 0.25, a = 1.0 }
    self:addChild(self.btnScan)
    curY = curY + 45

    -- Status Log
    self.lblStatus = ISLabel:new(padX, curY, 20, "Listo para escanear.", 0.7, 0.9, 0.7, 1, UIFont.Small, true)
    self:addChild(self.lblStatus)

    self:updatePresetFields("Todo Knox")
end

function AutomaticMapperUI:onSelectPreset()
    local selected = self.comboPresets:getOptionText(self.comboPresets.selected)
    self:updatePresetFields(selected)
end

function AutomaticMapperUI:updatePresetFields(presetName)
    local preset = AutomaticMapper.TownPresets[presetName]
    if preset then
        self.txtMinX:setText(tostring(preset.minX))
        self.txtMinY:setText(tostring(preset.minY))
        self.txtMaxX:setText(tostring(preset.maxX))
        self.txtMaxY:setText(tostring(preset.maxY))
    end
end

function AutomaticMapperUI:onTick(index, selected)
end

function AutomaticMapperUI:onStartScan()
    local minX = tonumber(self.txtMinX:getText()) or 0
    local minY = tonumber(self.txtMinY:getText()) or 0
    local maxX = tonumber(self.txtMaxX:getText()) or 30000
    local maxY = tonumber(self.txtMaxY:getText()) or 30000
    local radius = tonumber(self.txtRadius:getText()) or 35

    local bounds = { minX = minX, minY = minY, maxX = maxX, maxY = maxY }
    local ignoreWild = self.tickOptions:isSelected(self.optIgnoreWild)
    local includeObjects = self.tickOptions:isSelected(self.optObjects)
    local includeNearbyRoads = self.tickOptions:isSelected(self.optNearbyRoads)
    local includeNearbyBlds = self.tickOptions:isSelected(self.optNearbyBlds)
    local extractRooms = self.tickOptions:isSelected(self.optRooms)

    self.lblStatus:setName("Escaneando MetaGrid y objetos... por favor espera.")
    self.btnScan:setEnable(false)

    local scanResult = AutomaticMapper.Core.scanMap({
        bounds = bounds,
        ignoreWilderness = ignoreWild,
        extractRooms = extractRooms,
        includeObjects = includeObjects,
        includeNearbyRoads = includeNearbyRoads,
        includeNearbyBlds = includeNearbyBlds,
        proximityRadius = radius
    })

    if scanResult then
        local filename = "AutomaticMapper_Export.json"
        local success = AutomaticMapper.Core.exportToFile(scanResult, filename)
        if success then
            local msg = string.format("Exito! %d casas, %d habitaciones. Guardado en: Zomboid/Lua/%s",
                scanResult.counts.buildings, scanResult.counts.rooms, filename)
            self.lblStatus:setName(msg)
        else
            self.lblStatus:setName("Error al escribir el archivo.")
        end
    else
        self.lblStatus:setName("Fallo en el escaneo de MetaGrid.")
    end

    self.btnScan:setEnable(true)
end

local function onFillWorldObjectContextMenu(player, context, worldobjects, test)
    context:addOption("Abrir AutomaticMapper", nil, function()
        if not AutomaticMapperUI.instance then
            AutomaticMapperUI.instance = AutomaticMapperUI:new(180, 160, 380, 390)
            AutomaticMapperUI.instance:initialise()
            AutomaticMapperUI.instance:addToUIManager()
        else
            AutomaticMapperUI.instance:setVisible(not AutomaticMapperUI.instance:getIsVisible())
        end
    end)
end

Events.OnFillWorldObjectContextMenu.Add(onFillWorldObjectContextMenu)
