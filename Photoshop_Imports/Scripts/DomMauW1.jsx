// Photoshop Script: Đổ màu spot channel W1 (đỏ CMYK) và lưu .TIF lossless
// Dùng khi chạy thủ công trong Photoshop với ảnh đang mở.

#target photoshop
app.displayDialogs = DialogModes.NO;

var CHANNEL_NAME = "W1";
var CYAN = 0;
var MAGENTA = 100;
var YELLOW = 100;
var BLACK = 0;
var SOLIDITY = 70;

function hasSelection(doc) {
    try {
        var bounds = doc.selection.bounds;
        return bounds[0] !== bounds[2] && bounds[1] !== bounds[3];
    } catch (e) {
        return false;
    }
}

function loadTransparencySelection(doc) {
    try {
        doc.selection.load(doc.channels.getByName("Transparency"), SelectionType.REPLACE);
        return hasSelection(doc);
    } catch (e) {
        return false;
    }
}

function selectSubject() {
    try {
        executeAction(stringIDToTypeID("subjectSelect"), new ActionDescriptor(), DialogModes.NO);
        return true;
    } catch (e) {
        return false;
    }
}

function selectArtwork(doc) {
    if (loadTransparencySelection(doc)) {
        return;
    }
    if (selectSubject() && hasSelection(doc)) {
        return;
    }
    doc.selection.selectAll();
}

function convertToCMYK(doc) {
    if (doc.mode === DocumentMode.CMYK) {
        return;
    }
    doc.changeMode(ChangeMode.CMYK);
}

function removeExistingSpotChannel(doc, channelName) {
    for (var i = doc.channels.length - 1; i >= 0; i--) {
        var channel = doc.channels[i];
        if (channel.kind === ChannelType.SPOTCOLOR && channel.name === channelName) {
            channel.remove();
        }
    }
}

function createSpotChannelFromSelection(doc) {
    var spotColor = new SolidColor();
    spotColor.cmyk.cyan = CYAN;
    spotColor.cmyk.magenta = MAGENTA;
    spotColor.cmyk.yellow = YELLOW;
    spotColor.cmyk.black = BLACK;

    var spotChannel = doc.channels.add();
    spotChannel.kind = ChannelType.SPOTCOLOR;
    spotChannel.name = CHANNEL_NAME;
    spotChannel.color = spotColor;
    spotChannel.opacity = SOLIDITY;

    if (hasSelection(doc)) {
        var processChannels = doc.componentChannels;
        doc.activeChannels = [spotChannel];
        var fillDesc = new ActionDescriptor();
        fillDesc.putEnumerated(
            charIDToTypeID("Usng"),
            charIDToTypeID("FlCn"),
            charIDToTypeID("Wht ")
        );
        executeAction(charIDToTypeID("Fl  "), fillDesc, DialogModes.NO);
        doc.activeChannels = processChannels;
    }
}

function saveLosslessTiff(doc) {
    var saveFile;
    try {
        if (doc.saved) {
            var docName = doc.name.replace(/\.[^\.]+$/, "");
            saveFile = new File(doc.path + "/" + docName + ".tif");
        }
    } catch (e) {}

    if (!saveFile) {
        saveFile = File.saveDialog("Lưu file .TIF spot W1", "TIFF (*.tif):*.tif");
    }
    if (!saveFile) {
        return;
    }

    var tiffOpts = new TiffSaveOptions();
    tiffOpts.embedColorProfile = true;
    tiffOpts.imageCompression = TIFFEncoding.NONE;
    tiffOpts.byteOrder = ByteOrder.IBM;
    tiffOpts.layers = false;
    tiffOpts.spotColors = true;
    tiffOpts.alphaChannels = false;
    tiffOpts.saveImagePyramid = false;
    tiffOpts.annotations = false;
    doc.saveAs(saveFile, tiffOpts, true);
    alert("Da luu spot W1 thanh cong:\n" + decodeURI(saveFile.fullName));
}

if (app.documents.length === 0) {
    alert("Vui long mo anh truoc khi chay script DomMauW1.");
} else {
    var doc = app.activeDocument;
    selectArtwork(doc);
    convertToCMYK(doc);
    removeExistingSpotChannel(doc, CHANNEL_NAME);
    createSpotChannelFromSelection(doc);
    doc.selection.deselect();
    saveLosslessTiff(doc);
}