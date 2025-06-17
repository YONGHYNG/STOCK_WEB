package list.community.service;

import list.community.dto.DogdripPost;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

@Service
public class DogDripService {

    public List<DogdripPost> getPopularPosts() {
        List<DogdripPost> posts = new ArrayList<>();
        String url = "https://www.dogdrip.net/?mid=dogdrip&sort_index=popular";

        try {
            Document doc = Jsoup.connect(url)
                    .userAgent("Mozilla/5.0")
                    .timeout(10000)
                    .get();

            Elements items = doc.select("li.ed.flex.flex-left.flex-middle.webzine");

            int count = 0;
            for(Element item : items) {
                Element titleElement = item.selectFirst("a.ed.overlay");
                Element replyElement = item.selectFirst("span.replyNum");
                Element likeElement = item.selectFirst("span.unicon-up");

                if(titleElement != null && likeElement != null) {
                    String title = titleElement.text();
                    String likes = likeElement.text();
                    String replys = replyElement != null ? replyElement.text().replaceAll("[()]", "") : "0";

                    DogdripPost post = new DogdripPost(title, likes, replys);
                    posts.add(post);

                    // 콘솔 출력 추가
                    System.out.println("제목: " + title);
                    System.out.println("좋아요: " + likes);
                    System.out.println("댓글 수: " + replys);
                    System.out.println("----------------------");

                    count++;
                }

                if(count >= 10) break;
            }

        } catch(Exception e) {
            System.out.println("크롤링 중 오류 발생:");
            e.printStackTrace();
        }

        // 크롤링된 게시글 수 확인용 출력
        System.out.println("총 크롤링된 게시글 수: " + posts.size());

        return posts;
    }
}

