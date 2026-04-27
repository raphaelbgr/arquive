import SwiftUI

struct GalleryView: View {
    @State private var items: [ArquiveMedia] = []
    @State private var loading = true
    @State private var errorText: String?

    private let api = ArquiveAPI.shared
    private let columns = [GridItem(.adaptive(minimum: 400), spacing: 50)]

    var body: some View {
        NavigationView {
            Group {
                if loading {
                    ProgressView("Loading…")
                        .scaleEffect(2.0)
                } else if let err = errorText {
                    VStack(spacing: 30) {
                        Image(systemName: "wifi.exclamationmark")
                            .font(.system(size: 80))
                            .foregroundColor(.orange)
                        Text("Couldn't reach Arquive server").font(.title2)
                        Text(err).foregroundColor(.gray).font(.callout)
                        Text(api.baseURL.absoluteString)
                            .font(.caption).foregroundColor(.secondary)
                            .padding(.top, 10)
                        Button("Retry") { Task { await load() } }
                            .padding(.top, 20)
                    }
                    .padding(60)
                } else if items.isEmpty {
                    VStack {
                        Image(systemName: "photo.on.rectangle.angled")
                            .font(.system(size: 80))
                            .foregroundColor(.secondary)
                        Text("No media yet").font(.title2).padding(.top, 20)
                    }
                } else {
                    ScrollView {
                        LazyVGrid(columns: columns, spacing: 60) {
                            ForEach(items) { item in
                                MediaTile(media: item, baseURL: api.baseURL)
                            }
                        }
                        .padding(60)
                    }
                }
            }
            .navigationTitle("Arquive")
        }
        .task { await load() }
    }

    private func load() async {
        loading = true
        errorText = nil
        do {
            let response = try await api.fetchMedia()
            items = response.items
        } catch {
            errorText = error.localizedDescription
        }
        loading = false
    }
}

private struct MediaTile: View {
    let media: ArquiveMedia
    let baseURL: URL

    var body: some View {
        NavigationLink(destination: NativePlayerView(media: media, baseURL: baseURL)) {
            VStack(spacing: 12) {
                AsyncImage(url: media.thumbnailURL(base: baseURL)) { phase in
                    switch phase {
                    case .empty:
                        Rectangle().fill(Color.gray.opacity(0.2))
                            .overlay(ProgressView())
                    case .success(let image):
                        image.resizable().scaledToFill()
                    case .failure:
                        Rectangle().fill(Color.gray.opacity(0.2))
                            .overlay(
                                Image(systemName: media.isVideo ? "film" : "photo")
                                    .font(.largeTitle)
                                    .foregroundColor(.white)
                            )
                    @unknown default:
                        Rectangle().fill(Color.gray.opacity(0.2))
                    }
                }
                .frame(width: 400, height: 225)
                .clipped()
                .cornerRadius(12)

                Text(media.name)
                    .font(.headline)
                    .lineLimit(1)
                    .frame(maxWidth: 400)
            }
        }
        .buttonStyle(.card)
    }
}
