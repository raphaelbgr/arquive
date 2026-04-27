import Foundation

struct ArquiveMedia: Identifiable, Decodable {
    let id: Int
    let path: String
    let name: String
    let ext: String?
    let size: Int?
    let mimeType: String?
    let width: Int?
    let height: Int?
    let duration: Double?

    enum CodingKeys: String, CodingKey {
        case id, path, name, size, width, height, duration
        case ext = "extension"
        case mimeType = "mime_type"
    }

    var isVideo: Bool { (mimeType ?? "").hasPrefix("video/") }
    var isImage: Bool { (mimeType ?? "").hasPrefix("image/") }

    func thumbnailURL(base: URL) -> URL {
        base.appendingPathComponent("api/v1/media/\(id)/thumbnail")
    }

    func streamURL(base: URL) -> URL {
        base.appendingPathComponent("api/v1/media/\(id)/download")
    }
}

struct MediaListResponse: Decodable {
    let items: [ArquiveMedia]
    let total: Int
    let page: Int
    let pages: Int
}
