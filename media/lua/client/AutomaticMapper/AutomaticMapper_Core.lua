--[[
    AutomaticMapper_Core.lua
    Motor de extracción espacial in-game para Project Zomboid (Build 42)
--]]

require "AutomaticMapper_Shared"

AutomaticMapper = AutomaticMapper or {}
AutomaticMapper.Core = AutomaticMapper.Core or {}

local function serializeValue(val)
    local t = type(val)
    if t == "number" then
        return tostring(val)
    elseif t == "boolean" then
        return val and "true" or "false"
    elseif t == "string" then
        return string.format("%q", val)
    elseif t == "table" then
        local isArray = (#val > 0)
        local parts = {}
        if isArray then
            for i = 1, #val do
                table.insert(parts, serializeValue(val[i]))
            end
            return "[" .. table.concat(parts, ",") .. "]"
        else
            for k, v in pairs(val) do
                table.insert(parts, string.format("%q:%s", tostring(k), serializeValue(v)))
            end
            return "{" .. table.concat(parts, ",") .. "}"
        end
    end
    return "null"
end

local function classifySpriteName(s)
    if not s then return "Objeto desconocido" end
    local lower = string.lower(s)
    if string.find(lower, "street_decoration_01_8") or string.find(lower, "street_decoration_01_9") or string.find(lower, "location_sewer") then
        return "Tapa de alcantarilla"
    elseif string.find(lower, "trafficlines") then
        return "Línea de tráfico"
    elseif string.find(lower, "curb") then
        return "Bordillo"
    elseif string.find(lower, "crate") or string.find(lower, "storage") or string.find(lower, "container") then
        return "Contenedor"
    elseif string.find(lower, "generator") then
        return "Generador"
    elseif string.find(lower, "door") then
        return "Puerta"
    elseif string.find(lower, "window") then
        return "Ventana"
    end
    return "Mueble / Decoración"
end

function AutomaticMapper.Core.scanMap(options)
    options = options or {}
    local bounds = options.bounds
    local ignoreWilderness = (options.ignoreWilderness ~= false)
    local extractRooms = (options.extractRooms ~= false)
    local includeObjects = (options.includeObjects ~= false)
    local includeNearbyRoads = (options.includeNearbyRoads ~= false)
    local includeNearbyBlds = (options.includeNearbyBlds ~= false)
    local radius = options.proximityRadius or 35
    
    local metaGrid = IsoWorld.instance:getMetaGrid()
    if not metaGrid then
        print("[AutomaticMapper] ERROR: MetaGrid no está disponible. ¿Estás dentro de una partida?")
        return nil
    end

    print("[AutomaticMapper] Iniciando escaneo ampliado...")
    local startTime = getTimestampMs()
    
    local result = {
        meta = {
            version = AutomaticMapper.Version,
            gameVersion = getCore():getVersionNumber(),
            timestamp = getTimestamp(),
            bounds = bounds or "full_knox",
            radius = radius
        },
        buildings = {},
        roads = {},
        zones = {},
        detectedObjects = {},
        wildernessEnvelope = nil,
        counts = {
            buildings = 0,
            rooms = 0,
            zones = 0,
            specialObjects = 0,
            wildernessCompacted = 0
        }
    }

    -- 1. EDIFICIOS Y CASAS
    local buildingsList = metaGrid:getBuildings()
    local bldCount = buildingsList:size()

    for i = 0, bldCount - 1 do
        local bld = buildingsList:get(i)
        local bx, by = bld:getX(), bld:getY()
        local bx2, by2 = bld:getX2(), bld:getY2()

        if AutomaticMapper.isInBounds(bx, by, bx2, by2, bounds) then
            local bldId = AutomaticMapper.getBuildingId(bld)
            local category = "General"
            if bld:isResidential() then category = "Residential"
            elseif bld:isShop() then category = "Commercial"
            elseif bld:isRural() then category = "Rural"
            elseif bld:isBasement() then category = "Basement"
            end

            local bldData = {
                id = bldId,
                cat = category,
                box = { bx, by, bx2, by2 },
                center = { math.floor((bx + bx2) / 2), math.floor((by + by2) / 2) },
                area = bld:getArea(),
                rooms = {}
            }

            if extractRooms then
                local roomsList = bld:getRooms()
                local rCount = roomsList:size()
                for r = 0, rCount - 1 do
                    local room = roomsList:get(r)
                    local rName = room:getName() or "unnamed"
                    local rLevel = room:getZ()
                    local rectsList = room:getRects()
                    local rects = {}

                    for rc = 0, rectsList:size() - 1 do
                        local rect = rectsList:get(rc)
                        local rx = (rect.getX and rect:getX()) or rect.x or 0
                        local ry = (rect.getY and rect:getY()) or rect.y or 0
                        local rw = (rect.getW and rect:getW()) or rect.w or 0
                        local rh = (rect.getH and rect:getH()) or rect.h or 0
                        table.insert(rects, { rx, ry, rw, rh })
                    end

                    table.insert(bldData.rooms, {
                        name = rName,
                        lvl = rLevel,
                        rects = rects
                    })
                    result.counts.rooms = result.counts.rooms + 1
                end
            end

            table.insert(result.buildings, bldData)
            result.counts.buildings = result.counts.buildings + 1
        end
    end

    -- 2. ZONAS Y CARRETERAS
    local zonesList = metaGrid:getZones()
    local zoneCount = zonesList:size()

    local wildMinX, wildMinY = 999999, 999999
    local wildMaxX, wildMaxY = -999999, -999999
    local hasWild = false

    for z = 0, zoneCount - 1 do
        local zone = zonesList:get(z)
        local zType = zone:getType() or "Unknown"
        local zx, zy = zone:getX(), zone:getY()
        local zx2, zy2 = zx + zone:getWidth(), zy + zone:getHeight()

        if AutomaticMapper.isInBounds(zx, zy, zx2, zy2, bounds) then
            local isForest = (zType == "Forest" or zType == "DeepForest" or zType == "Vegitation")
            
            if ignoreWilderness and isForest then
                if zx < wildMinX then wildMinX = zx end
                if zy < wildMinY then wildMinY = zy end
                if zx2 > wildMaxX then wildMaxX = zx2 end
                if zy2 > wildMaxY then wildMaxY = zy2 end
                hasWild = true
                result.counts.wildernessCompacted = result.counts.wildernessCompacted + 1
            else
                local zoneEntry = {
                    id = string.format("z_%s_%d", AutomaticMapper.sanitizeName(zType), z),
                    name = zone:getName() or "",
                    type = zType,
                    box = { zx, zy, zx2, zy2 }
                }
                table.insert(result.zones, zoneEntry)
                result.counts.zones = result.counts.zones + 1
            end
        end
    end

    if hasWild then
        result.wildernessEnvelope = {
            desc = string.format("Envolvente de bosques compactados (%d zonas)", result.counts.wildernessCompacted),
            minX = wildMinX, minY = wildMinY, maxX = wildMaxX, maxY = wildMaxY,
            corners = {
                topLeft = { x = wildMinX, y = wildMinY },
                topRight = { x = wildMaxX, y = wildMinY },
                bottomLeft = { x = wildMinX, y = wildMaxY },
                bottomRight = { x = wildMaxX, y = wildMaxY }
            }
        }
    end

    -- 3. OBJETOS DETALLADOS DEL MUNDO (Alcantarillas, Contenedores, Muebles)
    if includeObjects and getCell() then
        local currentCell = getCell()
        -- Escaneamos los objetos de los squares actualmente cargados
        for _, bld in ipairs(result.buildings) do
            local bx1, by1 = bld.box[1], bld.box[2]
            local bx2, by2 = bld.box[3], bld.box[4]
            -- Inspeccionamos una muestra representativa de cada edificio
            local sampleSq = currentCell:getGridSquare(math.floor((bx1+bx2)/2), math.floor((by1+by2)/2), 0)
            if sampleSq then
                local objs = sampleSq:getObjects()
                for o = 0, objs:size() - 1 do
                    local obj = objs:get(o)
                    local spr = obj:getSprite()
                    if spr then
                        local sprName = spr:getName()
                        local cat = classifySpriteName(sprName)
                        table.insert(result.detectedObjects, {
                            bldId = bld.id,
                            sprite = sprName,
                            category = cat
                        })
                        result.counts.specialObjects = result.counts.specialObjects + 1
                    end
                end
            end
        end
    end

    local elapsed = (getTimestampMs() - startTime) / 1000
    print(string.format("[AutomaticMapper] Escaneo finalizado en %.2f s. Edificios: %d, Habitaciones: %d, Zonas: %d",
        elapsed, result.counts.buildings, result.counts.rooms, result.counts.zones))

    return result
end

function AutomaticMapper.Core.exportToFile(data, filename)
    filename = filename or "AutomaticMapper_Export.json"
    print("[AutomaticMapper] Guardando archivo: " .. filename)

    local file = getFileWriter(filename, true, false)
    if not file then
        print("[AutomaticMapper] ERROR: No se pudo abrir el archivo para escritura: " .. filename)
        return false
    end

    local jsonString = serializeValue(data)
    file:write(jsonString)
    file:close()

    print("[AutomaticMapper] Archivo exportado con exito. Tamano aprox: " .. string.format("%.2f KB", string.len(jsonString) / 1024))
    return true
end
