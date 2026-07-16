// Photoshop Script: Xuất File Cắt (.AI) từ ảnh phủ đen (Silhouette)
// Định nghĩa các biến cơ bản
if (app.documents.length > 0) {
    var doc = app.activeDocument;
    
    // 1. Lưu lại vùng chọn hiện tại nếu có
    var hasSelection = false;
    try {
        doc.selection.bounds;
        hasSelection = true;
    } catch(e) {}

    // 2. Chọn các pixel màu đen (hoặc màu tối)
    try {
        selectBlackPixels();
    } catch(e) {
        alert("Không thể chọn vùng màu đen. Vui lòng kiểm tra lại ảnh!");
    }

    // 3. Tạo Work Path từ vùng chọn (Dùng tolerance = 1.0 pixel để đường cắt chính xác và mượt mà)
    try {
        doc.selection.makeWorkPath(1.0);
        doc.selection.deselect(); // Bỏ chọn vùng chọn sau khi đã tạo Path
    } catch(e) {
        alert("Không thể tạo đường dẫn cắt (Work Path) từ vùng chọn!");
    }

    // 4. Xác định nơi lưu file cắt (.AI)
    var saveFile;
    try {
        if (doc.saved) {
            // Nếu ảnh đã được lưu, mặc định lưu file AI cùng thư mục với tên dạng: ten_anh_cutting.ai
            var docName = doc.name.replace(/\.[^\.]+$/, ''); // Bỏ đuôi file
            saveFile = new File(doc.path + "/" + docName + "_cutting.ai");
        }
    } catch(e) {}

    if (!saveFile) {
        // Nếu ảnh chưa lưu hoặc gặp lỗi, hiển thị hộp thoại chọn nơi lưu
        saveFile = File.saveDialog("Chọn nơi lưu file vector cắt (.ai)", "Adobe Illustrator (*.ai):*.ai");
    }

    // 5. Xuất Work Path sang Illustrator (.AI)
    if (saveFile) {
        try {
            var exportOptions = new ExportOptionsIllustrator();
            exportOptions.path = IllustratorPathType.ALLPATHS; // Xuất tất cả các đường path (bao gồm Work Path)
            
            doc.exportDocument(saveFile, ExportType.ILLUSTRATORPATHS, exportOptions);
            
            // Xóa Work Path tạm thời để giữ file Photoshop sạch sẽ
            try {
                doc.pathItems.getByName("Work Path").remove();
            } catch(e) {}
            
            alert("Đã xuất file cắt vector thành công tại:\n" + decodeURI(saveFile.fullName));
        } catch(e) {
            alert("Lỗi khi xuất file cắt: " + e.message);
        }
    }
} else {
    alert("Vui lòng mở một ảnh silhouette (đã phủ đen) trước khi chạy script này!");
}

// Hàm chọn các pixel màu đen (Color Range Black) sử dụng Action Manager của Photoshop
function selectBlackPixels() {
    var idcolorRange = stringIDToTypeID("colorRange");
    var desc = new ActionDescriptor();
    var idT = charIDToTypeID("T   ");
    var descColor = new ActionDescriptor();
    descColor.putDouble(charIDToTypeID("Lmnc"), 0); // Lightness = 0 (Màu đen)
    descColor.putDouble(charIDToTypeID("A   "), 0);
    descColor.putDouble(charIDToTypeID("B   "), 0);
    desc.putObject(idT, charIDToTypeID("Clr "), descColor);
    desc.putInteger(charIDToTypeID("Fzns"), 120); // Độ dung sai (Fuzziness) = 120 để phủ hết biên màu đen
    executeAction(idcolorRange, desc, DialogModes.NO);
}
