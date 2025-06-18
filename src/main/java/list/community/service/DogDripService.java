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
        String url = "https://www.dogdrip.net/dogdrip";

        try {
            Document doc = Jsoup.connect(url)
                    .userAgent("Mozilla/5.0")
                    .timeout(10000)
                    .get();

            Elements titles = doc.select("a.ed.title-link");
            Elements metas = doc.select("div.ed.flex.list-meta");

            for (int i = 0; i < Math.min(10, titles.size()); i++) {
                String title = titles.get(i).text();

                // 댓글과 공감수 span 가져오기
                Elements counts = metas.get(i).select("span.ed.text-xxsmall.text-primary");
                String replys = counts.size() > 0 ? counts.get(0).text().trim() : "0";
                String likes = counts.size() > 1 ? counts.get(1).text().trim() : "0";

                posts.add(new DogdripPost(title, likes, replys));
            }

        } catch (Exception e) {
            e.printStackTrace();
        }

        return posts;
    }

}

