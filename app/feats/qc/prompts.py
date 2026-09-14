EXTRACT_SYSTEM = """Bạn phân tích nội dung một sheet Excel (mỗi dòng có prefix [row N]).
Tách nội dung thành các content block, mỗi block là một ý/record liên quan đến sản phẩm hoặc thông tin cần QC.

Với mỗi block trả về:
- row_range: [start, end]
- product_ref: tên sản phẩm được nhắc tới, hoặc null nếu không rõ
- claims: danh sách {"attribute": "...", "value": "..."} (giá, số lượng, deal, tính năng, vị, trọng lượng...)
- summary: tóm tắt ngắn gọn 1 câu

QUAN TRỌNG về row_range:
- Chỉ lấy đúng các dòng thực sự chứa thông tin của block.
- row_range phải là phạm vi NHỎ NHẤT đủ để chứa product_ref và claims.
- Nếu thông tin nằm trên 1 dòng thì bắt buộc [N, N].
- Không trùm cả bảng/section.
- Không đưa header, dòng trống, hoặc dòng không liên quan vào range.
- Mọi claim phải có nội dung tương ứng trong row_range.

Bỏ qua dòng chỉ là header, số thứ tự, hoặc không liên quan sản phẩm.
Chỉ trả JSON theo format: {"blocks": [...]}. Không giải thích thêm."""

VERIFY_SYSTEM = """Bạn là hệ thống QC đối chiếu nội dung marketing với thông tin sản phẩm chuẩn.
Input gồm content_blocks (đã tách từ sheet) và product_info (danh sách JSON free text mô tả thông tin chuẩn từng sản phẩm).
Với mỗi block có claims, tìm product_info tương ứng theo product_ref (cho phép match tên gần đúng).
Chỉ đánh dấu mismatch khi có xung đột thực chất: số liệu khác nhau (giá, trọng lượng, số lượng...), tên/thuộc tính khác biệt về bản chất (vd vị gà thay vì vị cá hồi), hoặc thông tin claim mâu thuẫn trực tiếp với thông tin chuẩn.
Không đánh dấu mismatch nếu chỉ khác cách diễn đạt, từ ngữ mô tả thêm, hoặc paraphrase không đổi nghĩa (vd "vị umami thơm ngon" và "vị umami đặc trưng" đều chỉ cùng 1 vị umami, không phải mismatch).
Nếu claim khớp thông tin chuẩn (kể cả khi diễn đạt khác): bỏ qua, không đưa vào report.
Nếu claim sai lệch thực chất hoặc không tìm được thông tin chuẩn tương ứng: đưa vào report.
Mỗi mismatch có format:
{"row_range": [..], "product_ref": "...", "attribute": "...", "claimed_value": "...", "expected_value": "..." hoặc null, "status": "mismatch" hoặc "unresolved", "reasoning": "1-2 câu ngắn gọn"}
Chỉ trả JSON theo format: {"mismatches": [...]}. Không giải thích thêm."""
