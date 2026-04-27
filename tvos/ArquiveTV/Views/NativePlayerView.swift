import SwiftUI
import AVKit

struct NativePlayerView: View {
    let media: ArquiveMedia
    let baseURL: URL

    @State private var player: AVPlayer?

    var body: some View {
        Group {
            if media.isVideo {
                VideoPlayer(player: player)
                    .ignoresSafeArea()
                    .onAppear {
                        let p = AVPlayer(url: media.streamURL(base: baseURL))
                        self.player = p
                        p.play()
                    }
                    .onDisappear { player?.pause() }
            } else {
                AsyncImage(url: media.streamURL(base: baseURL)) { phase in
                    switch phase {
                    case .success(let img):
                        img.resizable().scaledToFit()
                    case .failure:
                        VStack {
                            Image(systemName: "exclamationmark.triangle")
                                .font(.system(size: 80))
                            Text("Couldn't load image").padding(.top, 20)
                        }
                    default:
                        ProgressView().scaleEffect(2.0)
                    }
                }
                .ignoresSafeArea()
                .background(Color.black)
            }
        }
    }
}
