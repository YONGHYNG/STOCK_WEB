package list.community.service;

import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

@Service
public class ComService {

    private static final String BEST_URL = "https://www.fmkorea.com/best2";

    public List<String> getBestTitles() throws IOException {
        return fetchTitlesFromUrl(BEST_URL);
    }

    public List<String> fetchTitlesFromUrl(String url) throws IOException {
        Document doc = Jsoup.connect("https://www.fmkorea.com/best2")
                .userAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
                .referrer("https://www.google.com")
                .timeout(10 * 1000)
                .header("Accept-Language", "ko-KR,ko;q=0.9")
                .get();



        Elements elements = doc.select("div#bd_pc ul li h3.title > a");

        List<String> titles = new ArrayList<>();
        int count = 0;

        for (Element e : elements) {
            if (count >= 10) break;
            String title = e.text();
            System.out.println((count + 1) + ". " + title); // 제목 한 줄씩 출력
            titles.add(title);
            count++;
        }

        // 전체 리스트 한 번에 출력 (옵션)
        System.out.println("전체 타이틀 리스트: " + titles);

        return titles;
    }
}
