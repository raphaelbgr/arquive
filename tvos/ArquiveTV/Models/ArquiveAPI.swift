import Foundation

@MainActor
final class ArquiveAPI: ObservableObject {
    static let shared = ArquiveAPI()

    static let defaultServer = "http://192.168.7.13:64531"

    let baseURL: URL

    init() {
        let stored = UserDefaults.standard.string(forKey: "arquive.server")
        let urlString = (stored?.isEmpty == false ? stored : nil) ?? Self.defaultServer
        self.baseURL = URL(string: urlString!)!
    }

    func fetchMedia(page: Int = 1, limit: Int = 200) async throws -> MediaListResponse {
        var components = URLComponents(
            url: baseURL.appendingPathComponent("api/v1/media"),
            resolvingAgainstBaseURL: false
        )!
        components.queryItems = [
            URLQueryItem(name: "page", value: String(page)),
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "type", value: "media_only"),
        ]
        let (data, response) = try await URLSession.shared.data(from: components.url!)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw URLError(.badServerResponse)
        }
        return try JSONDecoder().decode(MediaListResponse.self, from: data)
    }
}
